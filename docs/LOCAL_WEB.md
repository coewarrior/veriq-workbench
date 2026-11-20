# 在本机运行 VERIQ 网页

使用 Linux 或 WSL2 中的 Linux 发行版，安装 Python 3.11+、Docker 和 OpenSSL。在仓库根目录运行以下命令。本例创建一个仅监听本机的专用 PostgreSQL 数据库，密码留在本地文件中。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

mkdir -p work
(umask 077; openssl rand -hex 32 > work/.db-password)
docker run -d --name veriq-local-db -p 127.0.0.1:15432:5432 \
  --mount "type=bind,src=$PWD/work/.db-password,dst=/run/secrets/veriq-db-password,readonly" \
  -e POSTGRES_DB=veriq -e POSTGRES_USER=veriq \
  -e POSTGRES_PASSWORD_FILE=/run/secrets/veriq-db-password postgres:17-bookworm
```

运行 `docker exec veriq-local-db pg_isready -h 127.0.0.1 -U veriq -d veriq`，看到 `accepting connections` 后再继续。

```bash
export API_TEST_DB_HOST=127.0.0.1 API_TEST_DB_PORT=15432
export API_TEST_DB_PASSWORD_FILE="$PWD/work/.db-password"
python -m api_test_tool.storage_migrate import-sqlite --allow-empty --source work/local-web
python -m api_test_tool.storage_migrate activate --revision "$(git rev-parse HEAD)"
python -m api_test_tool web --host 127.0.0.1 --port 18089 --data-dir work/local-web
```

打开 [http://127.0.0.1:18089/](http://127.0.0.1:18089/)。健康检查在 [`/healthz`](http://127.0.0.1:18089/healthz)。数据库初始化只需运行一次。以后可用 `docker start veriq-local-db` 启动数据库，重新设置上面的环境变量，再运行最后一条网页命令。

已有专用 PostgreSQL 时，可设置 `API_TEST_DB_HOST`、`API_TEST_DB_PORT`、`API_TEST_DB_NAME`、`API_TEST_DB_USER` 和 `API_TEST_DB_PASSWORD_FILE`，然后从空库初始化步骤继续。
