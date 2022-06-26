configurations = {
    "receiver": {
        "host": "10.10.2.2",
        "port": 50021
    },
    "data_dir": "/data/src_dir/",
    "method": "probe", #[gradient, bayes, random, brute, probe, cg, lbfgs]
    "bayes": {
        "initial_run": 3,
        "num_of_exp": -1
    },
    "random": {
        "num_of_exp": 10
    },
    "emulab_test": False,
    "centralized": False,
    "file_transfer": True,
    "B": 10,
    "K": 1.02,
    "loglevel": "info",
    "probing_sec": 3,
    "multiplier": 1,
    "mp_opt": False,
    "fixed_probing": {
        "bsize": 10,
        "thread": 5
    },
    "max_cc": 100,
}