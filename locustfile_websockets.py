from locust import HttpUser, task, events, between
from locust.event import EventHook
from dotenv import load_dotenv
import os
import time
import uuid
import json
import traceback
import websocket
import threading
import ssl

load_dotenv()

# Constants for token cost calculation
TOKEN_COST = {
    "input": {
        "llama3.2:1b": 0.003 / 1000,
        "bedrock_claude_haiku35_pipeline_mock": 0.0,
        "bedrock_claude_haiku35_pipeline": 0.0008 / 1000,
        "bedrock_llama32_11b_pipeline": 0.00016 / 1000,
        "bedrock_claude_sonnet35_v2_pipeline": 0.003 / 1000,
    },
    "output": {
        "llama3.2:1b": 0.015 / 1000,
        "bedrock_claude_haiku35_pipeline_mock": 0.0,
        "bedrock_claude_haiku35_pipeline": 0.004 / 1000,
        "bedrock_llama32_11b_pipeline": 0.00016 / 1000,
        "bedrock_claude_sonnet35_v2_pipeline": 0.015 / 1000,
    },
}

# Event hook for custom metrics
def log_custom_metrics(start_time, model_id, type, time_to_first_byte, time_to_first_token, 
                       total_time, num_output_tokens, tokens_per_second, content_validated, 
                       total_cost, status_code, **kwargs):
    pass

class WebSocketClient:
    """Custom WebSocket client wrapper for Locust"""
    def __init__(self, host, headers, locust_instance):
        self.host = host
        self.headers = headers
        self.locust_instance = locust_instance
        self.conn = None
        self.response_event = threading.Event()
        self.messages = []
        self.error = None
        self.is_open = False
    
    def connect(self, name=None):
        """Establish a WebSocket connection"""
        websocket_url = f"ws://{self.host.replace('http://', '').replace('https://', '')}/ws/socket.io/?EIO=4&transport=websocket"
        request_event = self.locust_instance.environment.events.request.fire
        start_time = time.time()
        
        try:
            self.conn = websocket.create_connection(
                websocket_url,
                header=["Cookie: token=" + self.headers.get("Authorization", "").replace("Bearer ", "")],
                enable_multithread=True,
                sslopt={"cert_reqs": ssl.CERT_NONE} if self.host.startswith("https") else {}
            )
            self.is_open = True
            request_event(
                request_type="WebSocket",
                name=name or "WebSocket Connect",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                exception=None,
                context={},
            )
            
            # Set up a listener thread for incoming messages
            self.listener_thread = threading.Thread(target=self._listen)
            self.listener_thread.daemon = True
            self.listener_thread.start()
            
            # Wait for the initial Socket.IO handshake messages
            self._handle_socketio_handshake()
            
            return True
        except Exception as e:
            self.error = str(e)
            request_event(
                request_type="WebSocket",
                name=name or "WebSocket Connect",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                exception=e,
                context={},
            )
            return False
    
    def _handle_socketio_handshake(self):
        """Handle the Socket.IO handshake protocol"""
        # Wait for the initial handshake message (typically "0{...}")
        if not self._wait_for_message(lambda msg: msg.startswith("0"), timeout=5):
            raise Exception("Socket.IO handshake failed - no initial message")
            
        # Send the Socket.IO "40" message (connect to default namespace)
        self.conn.send("40")
        
        # Wait for the connection confirmation (typically "40{...}")
        if not self._wait_for_message(lambda msg: msg.startswith("40"), timeout=5):
            raise Exception("Socket.IO handshake failed - no connection confirmation")
    
    def _wait_for_message(self, condition_func, timeout=30):
        """Wait for a specific message matching the condition function"""
        end_time = time.time() + timeout
        while time.time() < end_time:
            for msg in list(self.messages):
                if condition_func(msg):
                    self.messages.remove(msg)
                    return msg
            time.sleep(0.1)
        return None
    
    def _listen(self):
        """Background thread to listen for WebSocket messages"""
        while self.is_open and self.conn:
            try:
                message = self.conn.recv()
                self.messages.append(message)
                
                # If this is a completion message, set the event
                if "42[\"message\"" in message and "assistant" in message:
                    self.response_event.set()
            except Exception as e:
                if self.is_open:  # Only log errors if we're supposed to be connected
                    self.error = f"WebSocket receive error: {str(e)}"
                    self.is_open = False
                break
    
    def send_chat_message(self, payload, name=None):
        """Send a chat message over the WebSocket connection and wait for response"""
        if not self.is_open:
            return False, "WebSocket is not connected"
        
        request_event = self.locust_instance.environment.events.request.fire
        start_time = time.time()
        self.response_event.clear()  # Reset the event for the new message
        response_text = ""
        
        try:
            # Format the message as a Socket.IO event
            # Socket.IO message format: "42" + JSON array with event name and payload
            message = '42["message",' + json.dumps(payload) + ']'
            self.conn.send(message)
            
            # Wait for the response with a timeout
            if self.response_event.wait(timeout=60):  # 60-second timeout
                # Process received messages to extract the actual response
                for msg in list(self.messages):
                    if "42[\"message\"" in msg and "assistant" in msg:
                        response_text = msg
                        self.messages.remove(msg)
                        break
                
                request_event(
                    request_type="WebSocket",
                    name=name or "Chat Message",
                    response_time=(time.time() - start_time) * 1000,
                    response_length=len(response_text),
                    exception=None,
                    context={},
                )
                return True, response_text
            else:
                error_msg = "Timeout waiting for response"
                request_event(
                    request_type="WebSocket",
                    name=name or "Chat Message",
                    response_time=(time.time() - start_time) * 1000,
                    response_length=0,
                    exception=Exception(error_msg),
                    context={},
                )
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Error sending message: {str(e)}"
            request_event(
                request_type="WebSocket",
                name=name or "Chat Message",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                exception=e,
                context={},
            )
            return False, error_msg
    
    def close(self):
        """Close the WebSocket connection"""
        if self.is_open and self.conn:
            try:
                self.is_open = False
                self.conn.close()
            except:
                pass


class WebSocketUser(HttpUser):
    """Locust user class that uses WebSockets for communication"""
    wait_time = between(10, 30)
    host = os.getenv("GSAI_HOST")
    abstract = True
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ws_client = None
        self.start_time = time.time()
    
    def on_start(self):
        """Initialize the user session and WebSocket connection"""
        print("\n=== Host Configuration ===")
        print(f"Env var GSAI_HOST: {os.getenv('GSAI_HOST')}")
        print(f"Self.host value: {self.host}")
        print(f"Type of host: {type(self.host)}")
        
        # Set up HTTP headers for both HTTP requests and WebSockets
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
            "Cookie": f"token={auth_token}",
            "Content-Type": "application/json",
        }
        
        # Initialize WebSocket connection
        self.ws_client = WebSocketClient(self.host, self.client.headers, self)
        if not self.ws_client.connect("WebSocket Initial Connect"):
            print(f"Failed to establish WebSocket connection: {self.ws_client.error}")
    
    def on_stop(self):
        """Clean up when the user stops"""
        if self.ws_client:
            self.ws_client.close()


class WebSocketChatUser(WebSocketUser):
    """User that performs chat completions over WebSockets"""
    
    @task
    def chat_completion(self):
        """Send a chat completion request over WebSockets"""
        if not self.ws_client or not self.ws_client.is_open:
            # Try to reconnect if the connection is closed
            if not self.ws_client.connect("WebSocket Reconnect"):
                print(f"Failed to reconnect WebSocket: {self.ws_client.error}")
                return
        
        chat_id = str(uuid.uuid4())
        message_id = str(uuid.uuid4())
        current_time = int(time.time())
        
        print(f"\n=== Starting new WebSocket chat completion request ===")
        print(f"Chat ID: {chat_id}")
        print(f"Message ID: {message_id}")
        print(f"Current time: {current_time}")
        
        model_id = os.getenv("CHAT_MODEL")
        content = os.getenv("USER_PROMPT")
        content_validation_string = os.getenv("CONTENT_VALIDATION_STRING")
        num_input_tokens = len(content.split())
        # input_cost = num_input_tokens * TOKEN_COST["input"].get(model_id, 0.0001)  # Default if model not found
        
        # Prepare the chat message payload
        message_payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "model": model_id,
            "content": content,
            "role": "user",
            "stream": True,
            "params": {},
            "background_tasks": {"title_generation": False, "tags_generation": False},
            "features": {"web_search": False},
        }
        
        # Record metrics
        request_initiation_time = int(time.time() * 1000)
        
        # Send the message and wait for response
        success, response_text = self.ws_client.send_chat_message(message_payload, "/ws/chat/completions")
        
        if success:
            # Process the response
            try:
                # Parse the Socket.IO message (remove the "42["message"," prefix and trailing "]")
                response_json_str = response_text.replace('42["message",', '')[:-1]
                response_data = json.loads(response_json_str)
                
                # Extract and validate response content
                complete_text = ""
                content_validated = False
                
                if "content" in response_data:
                    complete_text = response_data["content"]
                    if content_validation_string and content_validation_string.lower() in complete_text.lower():
                        content_validated = True
                
                # Calculate metrics
                response_time = int(time.time() * 1000) - request_initiation_time
                num_output_tokens = len(complete_text.split())
                # output_cost = num_output_tokens * TOKEN_COST["output"].get(model_id, 0.0002)  # Default if model not found
                total_cost = input_cost + output_cost
                tokens_per_second = num_output_tokens / (response_time / 1000) if response_time > 0 else 0
                
                # Log success or failure
                if content_validated:
                    print(f"WebSocket chat completion success")
                else:
                    print(f"Content validation failed for text: ...{complete_text[:100]}")
                
                # Record custom metrics
                self.environment.custom_event.fire(
                    start_time=self.start_time,
                    model_id=model_id,
                    type="ws_chat_completion",
                    time_to_first_byte=0,  # This would need to be captured differently for WebSockets
                    time_to_first_token=0,  # This would need to be captured differently for WebSockets
                    total_time=response_time,
                    num_output_tokens=num_output_tokens,
                    tokens_per_second=tokens_per_second,
                    content_validated=content_validated,
                    total_cost=total_cost,
                    status_code=200 if content_validated else 400,
                )
                
            except Exception as e:
                error_msg = f"Error processing WebSocket response: {str(e)}"
                full_traceback = traceback.format_exc()
                print(f"\nException occurred: {error_msg}")
                print(f"Full traceback:\n{full_traceback}")
                
                self.environment.custom_event.fire(
                    start_time=self.start_time,
                    model_id=model_id,
                    type="ws_chat_completion",
                    time_to_first_byte=0,
                    time_to_first_token=0,
                    total_time=int(time.time() * 1000) - request_initiation_time,
                    num_output_tokens=0,
                    tokens_per_second=0,
                    content_validated=False,
                    total_cost=0,  # Only input cost since we couldn't process the output
                    status_code=500,
                )
        else:
            print(f"WebSocket chat completion failed: {response_text}")
            
            self.environment.custom_event.fire(
                start_time=self.start_time,
                model_id=model_id,
                type="ws_chat_completion",
                time_to_first_byte=0,
                time_to_first_token=0,
                total_time=int(time.time() * 1000) - request_initiation_time,
                num_output_tokens=0,
                tokens_per_second=0,
                content_validated=False,
                total_cost=0,  # Only input cost since we couldn't get output
                status_code=500,
            )
            
        print("=== WebSocket chat completion request finished ===\n")

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