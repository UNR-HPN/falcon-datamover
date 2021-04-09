import socket
import numpy as np
import multiprocessing as mp
import logging
import time

HOST, PORT = "localhost", 32000
logger = mp.log_to_stderr(logging.DEBUG)
recv_buffer_size = 8192


def worker(client):
    while True:
        try:
            # client, address = sock.accept()
            # logger.debug("{u} connected".format(u=address))
            
            # client.sendall("start".encode('utf-8'))
            params = client.recv(recv_buffer_size).decode().split(",")
            cc = 0 if len(params) < 1 else int(params[0])
            count = 0
            
            while cc > 0:
                count += 1
                if count > 50:
                    thrpt = -1
                else:   
                    thrpt = min(20 * cc, np.random.randint(935,945))
                    
                time.sleep(1)
                output = str(thrpt)
                client.sendall(output.encode('utf-8'))
                params = client.recv(recv_buffer_size).decode().split(",")
                
                cc = 0 if len(params) < 1 else int(params[0])
                if len(params)>0:
                    logger.debug("parameters: {0}".format(params))
                
            client.close()
        except Exception as e:
            logger.error(str(e))
            

if __name__ == '__main__':
    num_workers = 1
    # sock = socket.socket()
    # sock.bind((HOST, PORT))
    # sock.listen(num_workers)
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))

    workers = [mp.Process(target=worker, args=(sock,)) for i in range(num_workers)]
    for p in workers:
        p.daemon = True
        p.start()

    while True:
        try:
            time.sleep(1)
        except:
            break