FROM python:3.12-alpine
WORKDIR /app
COPY . /app
RUN pip3 install -r requirements.txt -i https://mirrors.bfsu.edu.cn/pypi/web/simple
ENTRYPOINT python3 main.py