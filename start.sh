# bash -i
conda activate py3.11
uvicorn main:app --port 8010 --host 127.0.0.1 --log-config log.ini > /dev/null 2>&1 &