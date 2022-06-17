FROM python:3.8

RUN mkdir /app
COPY . /app/
WORKDIR /app
RUN cd /app && python -m pip install -r requirements.txt

CMD python main.py
