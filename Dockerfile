FROM langflowai/langflow:latest

# Copy custom components
COPY components/ /app/components/

# Copy flow definitions
COPY flows/ /app/flows/

# Copy prompt templates
COPY prompts/ /app/prompts/

# Environment variables (override at runtime)
ENV LANGFLOW_SECRET_KEY=${LANGFLOW_SECRET_KEY}

EXPOSE 7860

CMD ["langflow", "run", "--host", "0.0.0.0", "--port", "7860"]
