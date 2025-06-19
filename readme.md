# Developer notes
Restart docker
```shell
 docker-compose down --rmi all
 docker-compose up --build
```

Make a request
```shell
curl -X POST http://localhost:8000/download \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer SECRET" \
  -d '{"url": "https://x.com/PicturesFoIder/status/1917127296164507778","chat_id":"293754044"}'
```


Check the Redis
```shell
docker ps
docker exec -it yt-dlp-telegram-redis-1 redis-cli
```
```text
127.0.0.1:6379> keys *
1) "download_tasks"
127.0.0.1:6379> LRANGE download_tasks 0 -1
1) "{\"task_id\": \"668c14d1-cf68-45d0-8e8d-49df67b24e0c\", \"url\": \"http://example.com/file_to_download\", \"chat_id\": \"123\"}"
2) "{\"task_id\": \"1f69e3f9-3859-4500-8790-f891fa11d21f\", \"url\": \"http://example.com/file_to_download\", \"chat_id\": \"123\"}"
3) "{\"task_id\": \"c24ba5c3-03e8-4588-9eb0-e9492206297a\", \"url\": \"http://example.com/file_to_download\", \"chat_id\": \"123\"}"
```