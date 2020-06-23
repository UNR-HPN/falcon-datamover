import socket
import multiprocessing as mp
import logging
import time


logger = mp.log_to_stderr(logging.DEBUG)
HOST, PORT = "127.0.0.1", 50021

def worker(socket):
    while True:
        client, address = socket.accept()
        logger.debug("{u} connected".format(u=address))
        
        chunk = client.recv(BUFFER_SIZE)
        while chunk:
            chunk = client.recv(BUFFER_SIZE)


if __name__ == '__main__':
    num_workers = 5

    sock = socket.socket()
    sock.bind((HOST, PORT))
    sock.listen(num_workers)
    
    BUFFER_SIZE = 256 * 1024 * 1024
    total = 0

    workers = [mp.Process(target=worker, args=(sock,)) for i in range(num_workers)]
    for p in workers:
        p.daemon = True
        p.start()

    while True:
        try:
            time.sleep(10)
        except:
            break