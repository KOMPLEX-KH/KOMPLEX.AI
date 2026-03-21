# gRPC AI Service

## Overview

This gRPC service is used for internal communication between the Express backend and the FastAPI AI service. It replaces REST calls with a faster, strongly-typed protocol.

The service exposes two main methods:

- ExplainGemini: Handles general AI prompts with optional previous context
- ExplainTopic: Handles prompts that include additional topic content

Each request:
1. Validates the API key
2. Validates required fields
3. Builds a structured prompt using internal helper functions
4. Sends the prompt to the AI provider
5. Returns the generated result

---

## Running the service (FastAPI side)

Run:

    uv run main.py

This starts:
- gRPC server on localhost:50051
- FastAPI server on http://127.0.0.1:8000

The gRPC server runs in a background thread.

---

## Calling the service (Express side)

### Setup client

    const client = new AIService(
      "localhost:50051",
      grpc.credentials.createInsecure()
    );

---

### ExplainGemini

    const response = await new Promise((resolve, reject) => {
      grpcClient.ExplainGemini(
        {
          prompt,
          previous_context,
          response_type,
          api_key: process.env.INTERNAL_API_KEY,
        },
        (err, resp) => {
          if (err) return reject(err);
          resolve(resp);
        }
      );
    });

---

### ExplainTopic

    const response = await new Promise((resolve, reject) => {
      grpcClient.ExplainTopic(
        {
          prompt,
          topic_content,
          previous_context,
          response_type,
          api_key: process.env.INTERNAL_API_KEY,
        },
        (err, resp) => {
          if (err) return reject(err);
          resolve(resp);
        }
      );
    });

---

## Flow

Client → Express (REST) → gRPC → FastAPI → AI → Response