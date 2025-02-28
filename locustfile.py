from locust import HttpUser, events, task, between, run_single_user
from locust.event import EventHook
from dotenv import load_dotenv
import json
import os
import time
import uuid
import csv
import traceback

load_dotenv()

# https://aws.amazon.com/bedrock/pricing/
TOKEN_COST = {
    "input": {
        "bedrock_claude_haiku35_pipeline_mock": 0.0,
        "bedrock_claude_haiku35_pipeline": 0.0008 / 1000,
        "bedrock_llama32_11b_pipeline": 0.00016 / 1000,
        "bedrock_claude_sonnet35_v2_pipeline": 0.003 / 1000,
        "llama3.2:1b": 0.00016 / 1000,
    },
    "output": {
        "bedrock_claude_haiku35_pipeline_mock": 0.0,
        "bedrock_claude_haiku35_pipeline": 0.004 / 1000,
        "bedrock_llama32_11b_pipeline": 0.00016 / 1000,
        "bedrock_claude_sonnet35_v2_pipeline": 0.015 / 1000,
    },
}

CUSTOM_CSV_FILE_NAME = "custom_metrics"  # os.getenv("CUSTOM_CSV_FILE_NAME")

test_start_time = int(time.time())


def log_custom_metrics(
    type,
    model_id,
    start_time,
    time_to_first_byte,
    time_to_first_token,
    total_time,
    num_output_tokens,
    tokens_per_second,
    content_validated,
    total_cost,
    status_code,
):

    csv_path = f"{model_id}_{start_time}.csv"
    file_exists = os.path.isfile(csv_path)

    with open(csv_path, mode="a", newline="") as csv_file:
        fieldnames = [
            "type",
            "model_id",
            "time_to_first_byte",
            "time_to_first_token",
            "total_time",
            "num_output_tokens",
            "tokens_per_second",
            "content_validated",
            "total_cost",
            "status_code",
        ]
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

        # Write the header only if the file does not exist
        if not file_exists:
            writer.writeheader()

        # Write the custom metrics to the CSV file
        writer.writerow(
            {
                "type": type,
                "model_id": model_id,
                "time_to_first_byte": time_to_first_byte,
                "time_to_first_token": time_to_first_token,
                "total_time": total_time,
                "num_output_tokens": num_output_tokens,
                "tokens_per_second": tokens_per_second,
                "content_validated": content_validated,
                "total_cost": total_cost,
                "status_code": status_code,
            }
        )


class WebsiteUser(HttpUser):
    wait_time = between(10, 30)  # simulates user wait time between requests
    host = os.getenv("GSAI_HOST")
    start_time = None

    def on_start(self):
        print("\n=== Host Configuration ===")
        print(f"Env var GSAI_HOST: {os.getenv('GSAI_HOST')}")
        print(f"Self.host value: {self.host}")
        print(f"Type of host: {type(self.host)}")

        self.start_time = test_start_time
        session = os.getenv("SESSION")
        auth_token = os.getenv("GSA_AUTH_TOKEN")
        self.client.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:134.0) Gecko/20100101 Firefox/134.0",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Origin": f"{self.host}",
            "DNT": "1",
            "Connection": "keep-alive",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "Authorization": f"Bearer {auth_token}",
            # Make sure that headers are set across both test cases. 
            "Cookie": f"session={session}; token={auth_token}",
        }

    @task
    def chat_completion(self):
        chat_id = str(uuid.uuid4())
        message_id = str(uuid.uuid4())
        current_time = int(time.time())

        print(f"\n===Starting new chat completion request ===")
        print(f"Chat ID: {chat_id}")
        print(f"Message ID: {message_id}")
        print(f"Current time: {current_time}")

        model_id = os.getenv("CHAT_MODEL")
        content = os.getenv("USER_PROMPT")

        # Add application/json header
        headers = {"Content-Type": "application/json"}


        content_validation_string = os.getenv("CONTENT_VALIDATION_STRING")
        num_input_tokens = len(content.split())
        input_cost = num_input_tokens * TOKEN_COST["input"][model_id]

        completion_payload = {
            "stream": True,
            "model": model_id,
            "messages": [
                {
                    "role": "user",
                    "content": content,
                }
            ],
            "params": {},
            "background_tasks": {"title_generation": False, "tags_generation": False},
            "chat_id": chat_id,
            "features": {"web_search": False},
        }

        # request initiation time in milliseconds
        request_initiation_time = int(time.time() * 1000)
        with self.client.post(
            "/api/chat/completions",
            json=completion_payload,
            name="/api/chat/completions",
            catch_response=True,
            verify=False,
            stream=True,
            headers=headers,
        ) as response:
            try:
                content_validated = False
                finished = False
                failed = False
                num_chunks = 0
                response_text = ""
                complete_text = ""
                response_initiation_time = int(time.time() * 1000)
                time_to_last_byte = response_initiation_time
                time_to_first_byte = response_initiation_time - request_initiation_time
                time_to_first_token = 0
                # print(f"Time to first byte: {time_to_first_byte} ms")
                for chunk in response.iter_content(chunk_size=None):
                    response_text += chunk.decode("utf-8")
                    while "data:" in response_text:
                        chunk_initiation_time = int(time.time() * 1000)
                        if num_chunks == 0:
                            time_to_first_token = (
                                chunk_initiation_time - request_initiation_time
                            )
                            # print(f"Time to first token: {time_to_first_token} ms")

                        time_since_previous_chunk = (
                            chunk_initiation_time - time_to_last_byte
                        )

                        if time_since_previous_chunk > 10 * 1000:
                            response.failure(
                                f"Unnacceptable delay between tokens: {time_since_previous_chunk} ms"
                            )
                            failed = True
                            break
                        delimiter = "data: "
                        data_start = response_text.index(delimiter) + len(delimiter)
                        data_end = response_text.index("\n", data_start)
                        data_json = response_text[data_start:data_end]
                        response_text = response_text[data_end + 1 :]
                        if data_json.strip() == "[DONE]":
                            # print("Received [DONE] message")
                            finished = True
                            break
                        try:
                            data = json.loads(data_json)
                            if "choices" in data:
                                choices = data["choices"]
                                if (
                                    "finish_reason" in choices[0]
                                    and choices[0]["finish_reason"] == "stop"
                                ):
                                    # print("Received stop message")
                                    finished = True
                                    break
                                for choice in choices:
                                    if "delta" in choice:
                                        if "content" in choice["delta"]:
                                            complete_text += choice["delta"]["content"]
                                            tokens = choice["delta"]["content"].lower()
                                            if content_validation_string in tokens:
                                                content_validated = True
                                            num_chunks += 1
                                time_to_last_byte = int(time.time() * 1000)

                        except json.JSONDecodeError:
                            print(f"Failed to parse line: {data_json}")
                            continue

                    if finished or failed:
                        if content_validated:
                            response.success()
                            break
                        else:
                            response.failure(
                                f"Content validation fail for text (last 100 chars): ...{complete_text[:100]}"
                            )
                            break

                if response.status_code != 200:
                    error_msg = f"Received status code: {response.status_code}"
                    print(f"\nError: {error_msg}")
                    # print(f"Response content: {response.content}")
                    response.failure(error_msg)

                # print(f"Complete response text: {complete_text}")
                num_output_tokens = len(complete_text.split())
                output_cost = num_output_tokens * TOKEN_COST["output"][model_id]
                total_cost = input_cost + output_cost
                total_time = int(time.time() * 1000) - request_initiation_time
                tokens_per_second = num_output_tokens / (total_time / 1000)
                # print(f"Total response time: {total_time} ms")
                # print(f"Response tokens: {num_output_tokens}")
                # print(f"Response t/s: {tokens_per_second}")
                # print(f"Valid response: {content_validated}")
                # print(f"Total cost: {total_cost}")
                print(f"\nCompletion response status code: {response.status_code}\n")
                self.environment.custom_event.fire(
                    start_time=self.start_time,
                    model_id=model_id,
                    type="chat_completion",
                    time_to_first_byte=time_to_first_byte,
                    time_to_first_token=time_to_first_token,
                    total_time=total_time,
                    num_output_tokens=num_output_tokens,
                    tokens_per_second=tokens_per_second,
                    content_validated=content_validated,
                    total_cost=total_cost,
                    status_code=response.status_code,
                )

            except Exception as e:
                error_msg = f"Request failed: {str(e)}"
                full_traceback = traceback.format_exc()
                print(f"\nException occurred: {error_msg}")
                print(f"Full traceback:\n{full_traceback}")
                response.failure(error_msg)

        # dummy completed payload
        completed_payload = {
            "model": "bedrock_claude_haiku35_pipeline_mock",
            "messages": [
                {
                    "id": message_id,
                    "role": "user",
                    "content": content,
                    "timestamp": request_initiation_time,
                },
                {
                    "id": "930fc556-db14-4a04-9097-e454aa788491",
                    "role": "assistant",
                    "content": complete_text,
                    "timestamp": time_to_first_token,
                },
            ],
            "chat_id": chat_id,
            "session_id": "qTARVcxc0i6vumNPAAAB",
            "id": "930fc556-db14-4a04-9097-e454aa788491",
        }
        with self.client.post(
            "/api/chat/completed",
            json=completed_payload,
            name="/api/chat/completed",
            catch_response=True,
            verify=False,
            stream=False,
            headers=headers,
        ) as response:
            try:
                print(f"Completed response status: {response.status_code}\n")
            except:
                print(f"Failed to parse response: {response.text}\n")

        # print("=== Chat completion request finished ===\n")

    @task
    def file_upload(self):
        current_time = int(time.time())

        print(f"\n===Starting new file upload request ===")
        print(f"Current time: {current_time}")

        pdf_filepath = './test2.pdf'
        request_initiation_time = int(time.time() * 1000)
        total_time = 0
        try:
            with open(pdf_filepath, 'rb') as f:
            
                with self.client.post(
                    "/api/v1/files/",
                    files={"file": f},
                    catch_response=True,
                    stream=True
                ) as response:

                    try:
                        if response.status_code != 200:
                            error_msg = f"Received status code: {response.status_code}"
                            print(f"\nError: {error_msg}")
                            print(f"Response content: {response.content}")
                            response.failure(error_msg)

                        print(f"Total response time: {total_time} ms")
                        print(f"\nResponse status code: {response.status_code}\n")
                        print("=== PDF File upload finished ===\n")

                    except Exception as e:
                        total_time = int(time.time() * 1000) - request_initiation_time
                        error_msg = f"An error occured when trying to upload the file: {e}"
                        response.failure(e)

        except FileNotFoundError as fnfe:
            total_time = int(time.time() * 1000) - request_initiation_time
            error_msg = f"Error occurred trying to access the file {pdf_filepath}: {fnfe}"
            print(f"An error occurred trying to access the file {pdf_filepath}: {fnfe}")

    # Define a custom event for logging additional metrics
    @events.init.add_listener
    def on_locust_init(environment, **_kwargs):
        if not hasattr(environment, "custom_event"):
            environment.custom_event = EventHook()
        environment.custom_event.add_listener(log_custom_metrics)

    @events.test_stop.add_listener
    def on_test_stop(environment, **_kwargs):
        # Flush or process the collected custom metrics here if needed
        print("Test has stopped!")  # or use print statements for flush console output


# if launched directly for debugging, e.g. "python3 locustfile.py", not "locust -f locustfile.py"
if __name__ == "__main__":
    run_single_user(WebsiteUser)
