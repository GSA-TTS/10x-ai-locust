from locust import HttpUser, events, task, between, run_single_user
from locust.event import EventHook
from dotenv import load_dotenv
import json
import os
import time
import uuid
import csv

load_dotenv()

# https://aws.amazon.com/bedrock/pricing/
TOKEN_COST = {
    "input": {
        "bedrock_claude_haiku35_pipeline": 0.0008 / 1000,
        "bedrock_llama32_11b_pipeline": 0.00016 / 1000,
        "bedrock_claude_sonnet35_v2_pipeline": 0.003 / 1000,
    },
    "output": {
        "bedrock_claude_haiku35_pipeline": 0.004 / 1000,
        "bedrock_llama32_11b_pipeline": 0.00016 / 1000,
        "bedrock_claude_sonnet35_v2_pipeline": 0.015 / 1000,
    },
}

CUSTOM_CSV_FILE_PATH = os.getenv("CUSTOM_CSV_FILE_PATH")


def log_custom_metrics(
    type,
    time_to_first_byte,
    time_to_first_token,
    total_time,
    num_output_tokens,
    tokens_per_second,
    i_have_seen_paris,
    total_cost,
    status_code,
):

    # TODO: We should either create a unique id or timestamp test start and create new csv for new test
    file_exists = os.path.isfile(CUSTOM_CSV_FILE_PATH)
    with open(CUSTOM_CSV_FILE_PATH, mode="a", newline="") as csv_file:
        fieldnames = [
            "type",
            "time_to_first_byte",
            "time_to_first_token",
            "total_time",
            "num_output_tokens",
            "tokens_per_second",
            "i_have_seen_paris",
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
                "time_to_first_byte": time_to_first_byte,
                "time_to_first_token": time_to_first_token,
                "total_time": total_time,
                "num_output_tokens": num_output_tokens,
                "tokens_per_second": tokens_per_second,
                "i_have_seen_paris": i_have_seen_paris,
                "total_cost": total_cost,
                "status_code": status_code,
            }
        )


class WebsiteUser(HttpUser):
    wait_time = between(5, 45)  # simulates user wait time between requests
    host = os.getenv("GSAI_HOST")

    def on_start(self):
        print("\n=== Host Configuration ===")
        print(f"Env var GSAI_HOST: {os.getenv('GSAI_HOST')}")
        print(f"Self.host value: {self.host}")
        print(f"Type of host: {type(self.host)}")

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
            "Cookie": f"session={session}; token={auth_token}",
            "Content-Type": "application/json",
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

        content = "Please tell me the capital of France. Please write 2-3 paragraphs about the city."
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
            "background_tasks": {"title_generation": True, "tags_generation": False},
            "chat_id": chat_id,
            "features": {"web_search": False},
        }

        # print(f"\nSending request with payload:")
        # print(json.dumps(completion_payload, indent=2))
        # print(self.client.headers)

        # request initiation time in milliseconds
        request_initiation_time = int(time.time() * 1000)
        with self.client.post(
            "/api/chat/completions",
            json=completion_payload,
            name="/api/chat/completions",
            catch_response=True,
            stream=True,
        ) as response:
            try:
                i_have_seen_paris = False
                finished = False
                failed = False
                num_chunks = 0
                response_text = ""
                complete_text = ""
                response_initiation_time = int(time.time() * 1000)
                time_to_last_byte = response_initiation_time
                time_to_first_byte = response_initiation_time - request_initiation_time
                time_to_first_token = 0
                print(f"Time to first byte: {time_to_first_byte} ms")
                for chunk in response.iter_content(chunk_size=None):
                    chunk_initiation_time = int(time.time() * 1000)
                    if num_chunks == 0:
                        time_to_first_token = (
                            chunk_initiation_time - response_initiation_time
                        )
                        print(f"Time to first token: {time_to_first_token} ms")

                    time_since_previous_chunk = (
                        chunk_initiation_time - time_to_last_byte
                    )

                    if time_since_previous_chunk > 10 * 1000:
                        response.failure(
                            f"Unnacceptable delay between tokens: {time_since_previous_chunk} ms"
                        )
                        failed = True
                        break
                    response_text += chunk.decode("utf-8")
                    while "data:" in response_text:
                        delimiter = "data: "
                        data_start = response_text.index(delimiter) + len(delimiter)
                        data_end = response_text.index("\n", data_start)
                        data_json = response_text[data_start:data_end]
                        response_text = response_text[data_end + 1 :]
                        if data_json.strip() == "[DONE]":
                            print("Received [DONE] message")
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
                                            if "paris" in tokens:
                                                i_have_seen_paris = True
                                            num_chunks += 1
                                time_to_last_byte = int(time.time() * 1000)

                        except json.JSONDecodeError:
                            print(f"Failed to parse line: {data_json}")
                            continue
                    if finished or failed:
                        if i_have_seen_paris:
                            response.success()
                            break
                        else:
                            response.failure("I am finished. I never saw Paris.")
                            break

                if response.status_code != 200:
                    error_msg = f"Received status code: {response.status_code}"
                    print(f"\nError: {error_msg}")
                    print(f"Response content: {response.content}")
                    response.failure(error_msg)

                # print(f"Complete response text: {complete_text}")
                num_output_tokens = len(complete_text.split())
                output_cost = num_output_tokens * TOKEN_COST["output"][model_id]
                total_cost = input_cost + output_cost
                total_time = int(time.time() * 1000) - request_initiation_time
                tokens_per_second = num_output_tokens / (total_time / 1000)
                print(f"Total response time: {total_time} ms")
                print(f"Response tokens: {num_output_tokens}")
                print(f"Response t/s: {tokens_per_second}")
                print(f"Valid response: {i_have_seen_paris}")
                print(f"Total cost: {total_cost}")
                print(f"\nResponse status code: {response.status_code}\n")
                self.environment.custom_event.fire(
                    type="chat_completion",
                    time_to_first_byte=time_to_first_byte,
                    time_to_first_token=time_to_first_token,
                    total_time=total_time,
                    num_output_tokens=num_output_tokens,
                    tokens_per_second=tokens_per_second,
                    i_have_seen_paris=i_have_seen_paris,
                    total_cost=total_cost,
                    status_code=response.status_code,
                )

            except Exception as e:
                error_msg = f"Request failed: {str(e)}"
                print(f"\nException occurred: {error_msg}")
                response.failure(error_msg)

        print("=== Chat completion request finished ===\n")

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
