# gsai-load-testing

Load Testing Repo for GSAI

## Local Quickstart

Start the server locally, open in browser, send a completion, grab the bearer token and cookie (only the session value) and create and .env from the example file.

- Create a python `venv` via your preferred method.
- `pip install -r requirements.txt`
- `python locustfile.py`: will run continuously, nice for debugging, see below to run full locust server

## Overview

This repository contains a Locust load testing script designed to test the GSAI chat completion API under various load conditions. The script is configured to simulate user behavior, sending POST requests to the API and verifying the responses.

## File Structure

- `locustfile.py`: The main load testing script where the user behavior and tests are defined.
- `.env`: A file to store environment variables required for the test (must be created by the user).

## Prerequisites

Ensure you have Docker and Docker Compose installed on your machine.

## Environment Variables

Create an `.env` file from the sample.env

## How to Run

### Run via Locust web server

To run the load test with multiple workers, use Docker Compose:

```sh
locust --web-port 8089 --web-host 0.0.0.0
```

## Understanding `locustfile.py`
