import grpc
from concurrent import futures
import ai_pb2
import ai_pb2_grpc
from app.utils import (parse_response_type)
from app.instructions.general_preprompt import general_pre_prompt
from app.instructions.topic_preprompt import topic_pre_prompt
from app.core import setting
from app.core.gemini import call_gemini

class AIService(ai_pb2_grpc.AIServiceServicer):

    def ExplainGemini(self, request, context):
        
        if request.api_key != setting.INTERNAL_API_KEY:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Unauthorized")

        if not request.prompt:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Prompt is required")

        response_type = parse_response_type(request.response_type)

        prompt_text = general_pre_prompt(
            request.prompt,
            request.previous_context,
            response_type
        )

        response = call_gemini(prompt_text)

        return ai_pb2.Response(result=response)

    def ExplainTopic(self, request, context):
        if request.api_key != setting.INTERNAL_API_KEY:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid API key")

        if not request.prompt or not request.topic_content:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "Prompt and topic content are required"
            )

        response_type = parse_response_type(request.response_type)

        prompt_text = topic_pre_prompt(
            request.prompt,
            request.topic_content,
            request.previous_context,
            response_type
        )

        response = call_gemini(prompt_text)

        return ai_pb2.Response(result=response)


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    ai_pb2_grpc.add_AIServiceServicer_to_server(AIService(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    print("gRPC server running on port 50051")
    server.wait_for_termination()