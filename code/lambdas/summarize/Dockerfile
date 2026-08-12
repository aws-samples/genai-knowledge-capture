#checkov:skip=CKV_DOCKER_2:Using AWS Lambda container image
#checkov:skip=CKV_DOCKER_3:Base image from AWS already uses limited user
FROM public.ecr.aws/lambda/python:3.12@sha256:da65e34b539ef0ac96c700d106565d18b1b650b6ba5290a8a79d5f97945d52b1
RUN dnf install -y pango-1.48.10 && dnf clean all
COPY . ${LAMBDA_TASK_ROOT}
RUN pip install -r requirements.txt --no-cache-dir
CMD ["summarize.lambda_handler"]