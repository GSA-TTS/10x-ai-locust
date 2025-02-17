# gsai-load-testing

Load Testing Repo for GSAI

## Overview

This repository contains a Locust load testing script designed to test the GSAI chat completion API under various load conditions. The script is configured to simulate user behavior, sending POST requests to the API and verifying the responses.

## File Structure

- `locustfile.py`: The main load testing script where the user behavior and tests are defined.
- `.env`: A file to store environment variables required for the test (must be created by the user).

## Prerequisites

Ensure you have Docker and Docker Compose installed on your machine.

## Environment Variables

Create a `.env` file in the root directory of the project to store your environment variables. The `.env` file should contain the following:

```
GSAI_HOST=https://your-api-url.com
GSA_AUTH_TOKEN=your-auth-token
CHAT_MODEL=your-chat-model
```

- `GSAI_HOST`: The base URL of the GSAI API.
- `GSA_AUTH_TOKEN`: The authentication token for accessing the API.
- `CHAT_MODEL`: The model used for chat completions.

## How to Run

### Run via Docker with a Single Worker

You can run the load test using Docker with the following command:

```sh
docker run -p 8089:8089 -v $PWD:/mnt/locust locustio/locust -f /mnt/locust/locustfile.py
```

This command maps the current directory to `/mnt/locust` inside the Docker container, runs Locust, and exposes the Locust web interface on `http://localhost:8089`.

### Run via Docker Compose with Multiple Workers

To run the load test with multiple workers, use Docker Compose:

```sh
docker-compose up --scale worker=4
```

This command will start the Locust master and 4 worker nodes, distributing the load test across multiple workers. The Locust web interface will be available at `http://localhost:8089`.

## Understanding `locustfile.py`

The `locustfile.py` script defines the user behavior and API interaction for the load test. Here's a breakdown of its main components:

### `WebsiteUser` Class

```python
class WebsiteUser(HttpUser):
    wait_time = between(1, 5)
    host = os.getenv("GSAI_HOST")
```

- Inherits from `HttpUser` to define the behavior of a simulated user.
- Sets a wait time between tasks to mimic real user interactions.
- Retrieves the API host from environment variables.

### `on_start` Method

```python
def on_start(self):
    auth_token = os.getenv("GSA_AUTH_TOKEN")
    self.client.headers = {
        "Content-Type": "application/json",
        "Accept": "*/*",
        "Authorization": f"Bearer {auth_token}",
    }
```

- Configures headers for HTTP requests, including authorization.

### `chat_completion` Task

```python
@task
def chat_completion(self):
    chat_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    current_time = int(time.time())

    completion_payload = {
        "stream": True,
        "model": os.getenv("CHAT_MODEL"),
        "messages": [{"role": "user", "content": "Hello there!"}],
        "params": {},
        "background_tasks": {"title_generation": True, "tags_generation": True},
        "chat_id": chat_id,
        "features": {"web_search": False},
    }

    with self.client.post(
        "/api/chat/completions",
        json=completion_payload,
        name="/api/chat/completions",
        catch_response=True,
    ) as response:
        try:
            if response.status_code == 200:
                content = response.content.decode("utf-8")
                for line in content split("\n"):
                    if line.startswith("date: "):
                        try:
                            data = json.loads(line[6:])
                            if data == ["DONE"]:
                                break
                            else:
                                print(f"Received chunk: {json.dumps(data)}")
                        except json.JSONDecodeError:
                            continue
                response.success()
            else:
                response.failure(f"Received status code: {response.status_code}")
        except Exception as e:
            response.failure(f"Request failed: {str(e)}")
```

- Simulates user behavior by sending a POST request to the `/api/chat/completions` endpoint.
- Processes and validates the response, marking it as success or failure based on predefined criteria.

## Conclusion

This setup allows for effective load testing of the GSAI API, providing insights into its performance under various loads. By following the instructions above, you can run the load test locally or in a distributed manner using Docker Compose.
