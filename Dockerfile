FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home eventia && mkdir -p /app/data && chown -R eventia:eventia /app
USER eventia
EXPOSE 8000
CMD ["python", "manage.py", "run", "--host", "0.0.0.0"]
