import socket
import os
import numpy as np
import time
import warnings
import logging as log
import multiprocessing as mp
from threading import Thread
# from sendfile import sendfile
from config import configurations
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


root = configurations["data_dir"]["sender"]
probing_time = configurations["probing_sec"]
file_names = os.listdir(root) * configurations["multiplier"]
throughput_logs = []

chunk_size = mp.Value("i", 0)
num_workers = mp.Value("i", 0)
sample_phase = mp.Value("i", 0)
transfer_done = mp.Value("i", 0)
process_status = mp.Array("i", [0 for i in range(configurations["thread_limit"])])
transfer_status = mp.Array("i", [0 for i in range(len(file_names))])
active_files = mp.Array("i", [0 for i in range(len(file_names))])
file_offsets = mp.Array("d", [0.0 for i in range(len(file_names))])

HOST, PORT = configurations["receiver"]["host"], configurations["receiver"]["port"]
RCVR_ADDR = str(HOST) + ":" + str(PORT)


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


def worker(indx, l):
    file_count = len(active_files)
    while transfer_done.value == 0:
        if process_status[indx] == 0:
            if (file_count == np.sum(transfer_status)):
                transfer_done.value = 1
        else:
            while num_workers.value < 1:
                pass

            # log.debug("Start - {0}".format(indx))
            # start = time.time()
            
            try:
                sock = socket.socket()
                sock.settimeout(3)
                sock.connect((HOST, PORT))
                
                if emulab_test:
                    target, factor = 10, 10
                    max_speed = (target * 1000 * 1000)/8
                    second_target, second_data_count = int(max_speed/factor), 0

                for i in range(indx, len(file_names), num_workers.value):
                # while (np.sum(active_files) < file_count) and (process_status[indx] == 1):
                #     i = -1
                #     if np.sum(transfer_status) == 0:
                #         i = indx
                #     else:
                #         for j in range(file_count):
                #             if active_files[j] == 0:
                #                 active_files[j] == 1
                #                 i = j
                #                 break
                    
                #     if i == -1:
                #         process_status[indx] = 0
                #         break
                    
                    if process_status[indx] == 0:
                        break
                    
                    if transfer_status[i] == 0:
                        filename = root + file_names[i]
                        file = open(filename, "rb")
                        offset = file_offsets[i]

                        log.debug("starting {0}, {1}, {2}".format(indx, i, filename))
                        timer100ms = time.time()
                       
                        while process_status[indx] == 1:
                            if emulab_test:
                                buffer_size = min(chunk_size.value, second_target-second_data_count)
                                data_to_send = bytearray(buffer_size)
                                sent = sock.send(data_to_send)
                            else:
                                sent = sock.sendfile(file=file, offset=int(offset), count=chunk_size.value)
                                # sent = sendfile(sock.fileno(), file.fileno(), int(offset), int(chunk_size.value))
                                # data = os.preadv(file,chunk_size.value,offset)
                                
                            offset += sent
                            file_offsets[i] = offset

                            if emulab_test:
                                second_data_count += sent
                                if second_data_count >= second_target:
                                    second_data_count = 0
                                    while timer100ms + (1/factor) > time.time():
                                        pass
                                    
                                    timer100ms = time.time()

                            # duration = time.time() - start
                            # if (sample_phase.value == 1 and (duration > probing_time)):
                            #     if sent == 0:
                            #         transfer_status[i] = 1
                            #         log.debug("finished {0}, {1}, {2}".format(indx, i, filename))
                                    
                            #     process_status[indx] = 0
                            
                            if sent == 0:
                                transfer_status[i] = 1
                                log.debug("finished {0}, {1}, {2}".format(indx, i, filename)) 
                                break
                
                active_files[i] = transfer_status[i]
                process_status[indx] = 0
                sock.close()
            
            except socket.timeout as e:
                pass
                
            except Exception as e:
                log.error("Process: {0}, Error: {1}".format(indx, str(e)))
            
            # log.debug("End - {0}".format(indx))
    
    process_status[indx] == 0
    return True 


def get_chunk_size(unit):
    unit = max(unit, 0)
    return (2 ** unit) * 1024


def sample_transfer(params):
    global throughput_logs
    if transfer_done.value == 1:
        return 10 ** 10
        
    log.info("Sample Transfer -- Probing Parameters: {0}".format(params))
    if len(file_names) < num_workers.value:
        params[0] = len(file_names)
        log.info("Effective Concurrency: {0}".format(num_workers.value))
    
    num_workers.value = params[0]
    chunk_size.value = get_chunk_size(configurations["chunk_limit"])

    current_cc = np.sum(process_status)
    for i in range(configurations["thread_limit"]):
        if i < params[0]:
            if (i >= current_cc):
                process_status[i] = 1
        else:
            process_status[i] = 0

    log.debug("Active CC: {0}".format(np.sum(process_status)))
    time.sleep(probing_time-2.2)
    before_sc, before_rc, before_sq = tcp_stats(RCVR_ADDR)
    time.sleep(2)
    after_sc, after_rc, after_sq = tcp_stats(RCVR_ADDR)

    sc, rc, sq = after_sc - before_sc, after_rc - before_rc, np.abs(after_sq - before_sq)
    base = 20
    if sq < 2 ** base:
        sq = 2 ** base
        
    log.info("SC: {0}, RC: {1}".format(sc, rc))  
    thrpt = np.mean(throughput_logs[-2:])
    lr, C = 0, int(configurations["C"])
    if sc != 0:
        lr = rc/sc if sc>rc else 0
    
    score_value = thrpt * (1 - C * (((1/(1-lr))-1) + ((np.log2(sq)-base)/100))) 
    score_value = np.round(score_value * (-1), 4)
    
    log.info("Probing -- Throughput: {0}, Loss Rate: {1}%, SQ_rate: {2}%, Score: {3}".format(
        np.round(thrpt), np.round(lr*100, 2), (np.log2(sq)-base)/100, score_value))

    # while np.sum(process_status)>0:
    #     pass 

    return score_value


def normal_transfer(params):
    num_workers.value = params[0]
    chunk_size.value = get_chunk_size(configurations["chunk_limit"])
        
    log.info("Normal Transfer -- Probing Parameters: {0}".format([num_workers.value, chunk_size.value]))
    
    files_left = len(transfer_status) - np.sum(transfer_status)
    if files_left < num_workers.value:
        num_workers.value = files_left
        log.info("Effective Concurrency: {0}".format(num_workers.value))

    for i in range(num_workers.value):
        process_status[i] = 1
    
    while (np.sum(process_status) > 0) and (transfer_done.value == 0):
        pass

    
def run_transfer():
    sample_phase.value = 1

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
    
    sample_phase.value = 0
    if transfer_done.value == 0:
        normal_transfer(params)
    

def report_throughput(start_time):
    global throughput_logs
    previous_total = 0
    previous_time = 0

    while (len(transfer_status) > sum(transfer_status)) and (transfer_done.value == 0):
        t1 = time.time()
        time_since_begining = np.round(t1-start_time, 1)
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
    print(file_names)
    lock = mp.Lock()
    workers = [mp.Process(target=worker, args=(i, lock)) for i in range(configurations["thread_limit"])]
    for p in workers:
        p.daemon = True
        p.start()
    
    start = time.time()
    throughput_thread = Thread(target=report_throughput, args=(start,), daemon=True)
    throughput_thread.start()
    run_transfer()
    end = time.time()
            
    time_since_begining = np.round(end-start, 3)
    total = np.round(np.sum(file_offsets) / (1024*1024*1024), 3)
    thrpt = np.round((total*8*1024)/time_since_begining,2)
    log.info("Total: {0} GB, Time: {1} sec, Throughput: {2} Mbps".format(
        total, time_since_begining, thrpt))
    
    for p in workers:
        if p.is_alive():
            p.terminate()
            p.join(timeout=0.1)
