

chạy ở local trước để có telegram.session

sau đấy copy session file lên môi trường chạy


docker build -t auto-post-bot .


docker run --name auto-post-bot -v /root/app/auto-post-bot/config.json:/app/config.json -v /root/app/auto-post-bot/telegram.session:/app/telegram.session  auto-post-bot:latest