FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/services
RUN addgroup --system app && adduser --system --ingroup app app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /data/uploads && chown -R app:app /srv/services /data
USER app
ENV UPLOAD_FOLDER=/data/uploads DATABASE_URL=sqlite:////data/services.sqlite3 PORT=9900 HOST=0.0.0.0
EXPOSE 9900
CMD ["sh", "-c", "flask --app run.py db upgrade && gunicorn -w 4 -b 0.0.0.0:${PORT} 'app:create_app()'"]
