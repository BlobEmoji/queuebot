FROM gorialis/discord.py:alpine-rewrite

WORKDIR /app
ADD . /app

RUN pip install -r requirements.txt

CMD ["python", "run.py"]
