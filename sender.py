import os
import time
import socket
import warnings
import numpy as np
import logging as log
import multiprocessing as mp
from config import configurations
from threading import Thread, Lock
from concurrent.futures import ThreadPoolExecutor
from search import  base_optimizer, dummy, brute_force, hill_climb, gradient_ascent

warnings.filterwarnings("ignore", category=FutureWarning)
configurations["cpu_count"] = mp.cpu_count()
configurations["thread_limit"] = configurations['limits']["thread"]
configurations["chunk_limit"] = configurations['limits']["bsize"]
    
if configurations["thread_limit"] == -1:
    configurations["thread_limit"] = configurations["cpu_count"]
    
FORMAT = '%(asctime)s -- %(levelname)s: %(message)s'
if configurations["loglevel"] == "debug":
    log.basicConfig(format=FORMAT, datefmt='%m/%d/%Y %I:%M:%S %p', level=log.DEBUG)
    mp.log_to_stderr(log.DEBUG)
else:
    log.basicConfig(format=FORMAT, datefmt='%m/%d/%Y %I:%M:%S %p', level=log.INFO)

emulab_test = False
if "emulab_test" in configurations and configurations["emulab_test"] is not None:
    emulab_test = configurations["emulab_test"]


lock = Lock()
root = configurations["data_dir"]["sender"]
probing_time = configurations["probing_sec"]
file_names = os.listdir(root) * configurations["multiplier"]
file_count = len(file_names)
throughput_logs = []

chunk_size, num_workers, sample_phase, transfer_done = 0, 0, 0, 0
process_status = [0 for i in range(configurations["thread_limit"])]
transfer_complete = [0 for i in range(file_count)]
transfer_running = [0 for i in range(file_count)]
file_offsets = [0 for i in range(file_count)]

HOST, PORT = configurations["receiver"]["host"], configurations["receiver"]["port"]
RCVR_ADDR = str(HOST) + ":" + str(PORT)


def update_chunk_size(value):
    global chunk_size
    # with lock:
    chunk_size = value


def update_num_workers(value):
    global num_workers
    # with lock:
    num_workers = value


def update_sample_phase(value):
    global sample_phase
    # with lock:
    sample_phase = value
        

def update_transfer_done(value):
    global transfer_done
    # with lock:
    transfer_done = value


def update_process_status(indx, value):
    global process_status
    # with lock:
    process_status[indx] = value
        

def update_transfer_complete(indx, value):
    global transfer_complete
    # with lock:
    transfer_complete[indx] = value


def update_transfer_running(indx, value):
    global transfer_running
    # with lock:
    transfer_running[indx] = value
        

def update_file_offsets(indx, value):
    global file_offsets
    # with lock:
    file_offsets[indx] = value


def get_a_file_id():
    global file_count, transfer_running
    file_id = -1
    if True:
        for i in range(file_count):
            if transfer_running[i] == 0:
                update_transfer_running(i, 1)
                i = file_id
                break
    
    return file_id
        

def tcp_stats(addr):
    start = time.time()
    sent, retm, sq = 0, 0, 0
    try:
        data = os.popen("ss -ti").read().split("\n")

        for i in range(1,len(data)):
            if addr in data[i-1]:
                sq += int([i for i in data[i-1].split(" ") if i][2])
                parse_data = data[i].split(" ")
                for entry in parse_data:
                    if "data_segs_out" in entry:
                        sent += int(entry.split(":")[-1])
                        
                    if "retrans" in entry:
                        retm += int(entry.split("/")[-1])
                
    except:
        pass
    
    end = time.time()
    log.debug("Time taken to collect tcp stats: {0}ms".format(np.round((end-start)*1000)))
    log.debug("Send-Q: {0}".format(sq))
    return sent, retm, sq


def worker(process_id):
    global transfer_done, num_workers, chunk_size, sample_phase
    global transfer_running, process_status, transfer_complete, file_offsets
    
    file_count = len(transfer_running)
    while transfer_done == 0:
        if process_status[process_id] == 0:
            if (file_count == np.sum(transfer_complete)):
                update_transfer_done(1)
        else:
            while num_workers < 1:
                pass
    
            try:
                sock = socket.socket()
                sock.settimeout(3)
                sock.connect((HOST, PORT))
                
                if emulab_test:
                    target, factor = 10, 10
                    max_speed = (target * 1000 * 1000)/8
                    second_target, second_data_count = int(max_speed/factor), 0

                # for file_id in range(process_id, len(file_names), num_workers):
                while (np.sum(transfer_running) < file_count) and (process_status[process_id] == 1):
                    file_id = get_a_file_id()
                    if file_id == -1:
                        break

                    if transfer_complete[file_id] == 0:
                        filename = root + file_names[file_id]
                        with open(filename, "rb") as file:
                            offset = file_offsets[file_id]

                            log.debug("starting {0}, {1}, {2}".format(process_id, file_id, filename))
                            timer100ms = time.time()
                        
                            while process_status[process_id] == 1:
                                if emulab_test:
                                    buffer_size = min(chunk_size, second_target-second_data_count)
                                    data_to_send = bytearray(buffer_size)
                                    sent = sock.send(data_to_send)
                                else:
                                    sent = sock.sendfile(file=file, offset=int(offset), count=chunk_size)
                                    # data = os.preadv(file,chunk_size,offset)
                                    
                                offset += sent
                                update_file_offsets(file_id, offset)

                                if emulab_test:
                                    second_data_count += sent
                                    if second_data_count >= second_target:
                                        second_data_count = 0
                                        while timer100ms + (1/factor) > time.time():
                                            pass
                                        
                                        timer100ms = time.time()
                                
                                if sent == 0:
                                    update_transfer_complete(file_id, 1)
                                    log.debug("finished {0}, {1}, {2}".format(process_id, file_id, filename)) 
                                    break
                
                    if transfer_running[file_id] != transfer_complete[file_id]:
                        update_transfer_running(file_id, transfer_complete[file_id])
                
                if process_status[process_id] != 0:
                    update_process_status(process_id, 0)
                    
                sock.close()
            
            except socket.timeout as e:
                pass
                
            except Exception as e:
                log.error("Process: {0}, Error: {1}".format(process_id, str(e)))
    
    if process_status[process_id] != 0:
        update_process_status(process_id, 0)
        
    return True 


def get_chunk_size(unit):
    unit = max(unit, 0)
    return (2 ** unit) * 1024


def sample_transfer(params):
    global throughput_logs, num_workers, process_status
    
    if transfer_done == 1:
        return 10 ** 10
        
    log.info("Sample Transfer -- Probing Parameters: {0}".format(params))
    if len(file_names) < num_workers:
        params[0] = len(file_names)
        log.info("Effective Concurrency: {0}".format(num_workers))
    
    update_num_workers(params[0])
    current_cc = np.sum(process_status)
    for i in range(configurations["thread_limit"]):
        if i < params[0]:
            if (i >= current_cc):
                update_process_status(i, 1)
        else:
            update_process_status(i, 0)

    log.debug("Active CC: {0}".format(np.sum(process_status)))
    time.sleep(probing_time-2.2)
    before_sc, before_rc, before_sq = tcp_stats(RCVR_ADDR)
    time.sleep(2)
    after_sc, after_rc, after_sq = tcp_stats(RCVR_ADDR)

    sc, rc, sq = after_sc - before_sc, after_rc - before_rc, np.abs(after_sq - before_sq)
    base = 10
    if sq < 2 ** base:
        sq = 2 ** base
        
    log.info("SC: {0}, RC: {1}".format(sc, rc))  
    thrpt = np.mean(throughput_logs[-2:])
    lr, C1, C2 = 0, int(configurations["C"]), 2
    if sc != 0:
        lr = rc/sc if sc>rc else 0
    
    score_value = thrpt * (1 - (C1 * ((1/(1-lr))-1)) - (C2 * ((np.log2(sq)-base)/100))) 
    score_value = np.round(score_value * (-1), 4)
    
    log.info("Probing -- Throughput: {0}, Loss Rate: {1}%, SQ_rate: {2}%, Score: {3}".format(
        np.round(thrpt), np.round(lr*100, 2), (np.log2(sq)-base)/100, score_value))

    return score_value


def normal_transfer(params):
    global num_workers, process_status, transfer_done, num_workers
    
    update_num_workers(params[0])
    log.info("Normal Transfer -- Probing Parameters: {0}".format([num_workers]))
    
    files_left = len(transfer_complete) - np.sum(transfer_complete)
    if files_left < num_workers:
        update_num_workers(files_left)
        log.info("Effective Concurrency: {0}".format(num_workers))

    for i in range(num_workers):
        update_process_status(i, 1)
    
    while (np.sum(process_status) > 0) and (transfer_done == 0):
        pass

    
def run_transfer():
    global transfer_done
    update_sample_phase(1)

    if configurations["method"].lower() == "random":
        params = dummy(configurations, sample_transfer, log)
    
    elif configurations["method"].lower() == "brute":
        params = brute_force(configurations, sample_transfer, log)
    
    elif configurations["method"].lower() == "hill_climb":
        params = hill_climb(configurations, sample_transfer, log)
    
    elif configurations["method"].lower() == "gradient":
        params = gradient_ascent(configurations, sample_transfer, log)
    
    elif configurations["method"].lower() == "probe":
        params = [configurations["probe_config"]["thread"]]
        
    else:
        params = base_optimizer(configurations, sample_transfer, log)
    
    update_sample_phase(0)
    if transfer_done == 0:
        normal_transfer(params)
    

def report_throughput(start_time):
    global throughput_logs, transfer_complete, transfer_done
    previous_total = 0
    previous_time = 0

    while (len(transfer_complete) > sum(transfer_complete)) and (transfer_done == 0):
        t1 = time.time()
        time_since_begining = np.round(t1-start_time, 1)
        
        if time_since_begining > 0:
            total_bytes = np.sum(file_offsets)
            thrpt = np.round((total_bytes*8)/(time_since_begining*1000*1000), 2)
            
            curr_total = total_bytes - previous_total
            curr_time_sec = np.round(time_since_begining - previous_time, 3)
            curr_thrpt = np.round((curr_total*8)/(curr_time_sec*1000*1000), 2)
            previous_time, previous_total = time_since_begining, total_bytes
            throughput_logs.append(curr_thrpt)
            log.info("Throughput @{0}s: Current: {1}Mbps, Average: {2}Mbps".format(
                time_since_begining, curr_thrpt, thrpt))
            
        t2 = time.time()
        time.sleep(max(0, 1 - (t2-t1)))


if __name__ == '__main__':
    update_chunk_size(get_chunk_size(configurations["chunk_limit"]))
    
    workers = [Thread(target=worker, args=(indx,)) for indx in range(configurations["chunk_limit"])]
    for t in workers:
        t.start()
    
    start = time.time()
    reporting_thread = Thread(target=report_throughput, args=(start,))
    reporting_thread.start()
    run_transfer()
    end = time.time()
            
    time_since_begining = np.round(end-start, 3)
    total = np.round(np.sum(file_offsets) / (1024*1024*1024), 3)
    thrpt = np.round((total*8*1024)/time_since_begining,2)
    log.info("Total: {0} GB, Time: {1} sec, Throughput: {2} Mbps".format(
        total, time_since_begining, thrpt))
