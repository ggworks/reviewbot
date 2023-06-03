import os
import subprocess
import json
import fcntl
import logging
logger = logging.getLogger(__name__)

from . import lsp

EXECUTABLE_FILE_MASK = os.F_OK | os.X_OK

def GetExecutable( filename ):
  if ( os.path.isfile( filename )
       and os.access( filename, EXECUTABLE_FILE_MASK ) ):
    return filename
  return None

def set_non_blocking(process: subprocess.Popen):
    # get the current stdout flags
    flags = fcntl.fcntl(process.stdout, fcntl.F_GETFL)
    # set the stdout flags to non-blocking
    fcntl.fcntl(process.stdout, fcntl.F_SETFL, flags | os.O_NONBLOCK)

def read_response(process: subprocess.Popen):
    headers = {}
    while True:
        try:
            headerline = process.stdout.readline().strip()
        except IOError:
            continue
        if not headerline:
            break
        key, value = lsp.ToUnicode(headerline).split(':', 1)
        headers[key.strip()] = value.strip()

    if headers == {}:
        return None

    if 'Content-Length' not in headers:
        raise RuntimeError("Missing 'Content-Length' header")
    content_length = int(headers['Content-Length'])

    content = process.stdout.read(content_length)

    content_str = content.decode('utf-8')
    response = json.loads(content_str)

    return response


def read_response_of_request(process, request_id):
    answer = None
    
    while answer is None:
        if process.poll() is not None:
            logger.error('lsp process has terminated')
            break
        response = read_response(process)
        if response and 'id' in response:
            response_id = response['id']
            logger.info(f'lsp res:{response_id}, {response}')
            if response_id == request_id:
                answer = response
                return answer

    return answer

class LspProcess:
    def __init__(self) -> None:
        self.req_id = 0
        self.process = None

    def next_request_id(self):
        self.req_id += 1
        return self.req_id

    def start_server(self, server_path: str, args: list[str] = []):
        self.process = subprocess.Popen(
            [server_path, *args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        
        # set_non_blocking(self.process)

        return self.process

    def stop_server(self):
        self.process.kill()

    def send_request(self, request: bytes):
        self.process.stdin.write(request)
        self.process.stdin.flush()

    def initialize(self, root_path: str = None):
        request_id = self.next_request_id()
        request = lsp.Initialize(request_id, root_path, {}, {})
        
        logger.info(f'lsp init:{request_id}, path: {root_path}')
        
        self.send_request(request)

        answer = read_response_of_request(self.process, request_id)
        return answer is not None

    
    def open_file(self, file_path: str, file_type: str, file_content: str):
        request = lsp.DidOpenTextDocument(file_path, file_type, file_content)
        self.send_request(request)
        
    def get_symbols(self, file_path: str):
        logger.info(f'lsp get_symbols')

        request_id = self.next_request_id()
        request = lsp.DocumentSymbol(request_id, file_path)
        self.send_request(request)
        
        answer = read_response_of_request(self.process, request_id)
        return answer['result'] if answer else None
