"""
CLI interface for the simulator to access via gRPC, currently no mux scans
"""

import argparse
import logging
import os
import shutil
import signal
import time
import numpy as np
from pathlib import Path
from simreaduntil.shared_utils.debugging_helpers import is_test_mode
from simreaduntil.shared_utils.logging_utils import add_comprehensive_stream_handler_to_logger, print_logging_levels, setup_logger_simple
from simreaduntil.shared_utils.utils import print_args
from simreaduntil.simulator.gap_sampling.constant_gaps_until_blocked import ConstantGapsUntilBlocked
from simreaduntil.simulator.gap_sampling.rolling_window_gap_sampler import RollingWindowGapSamplerPerChannel
from simreaduntil.simulator.readpool import ReadPoolFromFile, ThreadedReadPoolWrapper
from simreaduntil.simulator.readswriter import CompoundReadsWriter, RotatingFileReadsWriter
from simreaduntil.simulator.simfasta_to_seqsum import SequencingSummaryWriter, convert_simfasta_dir_to_seqsum
from simreaduntil.simulator.simulator import ONTSimulator, write_simulator_stats
from simreaduntil.simulator.simulator_params import SimParams
from simreaduntil.simulator.simulator_server import launchable_device_grpc_server, manage_grpc_server
from simreaduntil.shared_utils.utils import set_signal_handler

logger = setup_logger_simple(__name__)
"""module logger"""

#AG has added in "CustomCompoundReadsWriter" class def
class CustomCompoundReadsWriter(CompoundReadsWriter):
    def __init__(self, *args, output_dir, **kwargs):
        super().__init__(*args, **kwargs)
        self.output_dir = output_dir

def parse_args(args=None):
    parser = argparse.ArgumentParser(description="Simple gRPC server exposing the ONT simulator given reads as input, see 'src/simreaduntil/usecase_helpers/simulator_with_readfish.py' for other options to use the simulator, e.g., from a genome and with mux scans, pore model for raw signal data")
    parser.add_argument("reads_file", type=Path, help="Path to the reads, e.g., generated by NanoSim or perfect reads")
    parser.add_argument("run_dir", type=Path, help="Run dir, must not exist", default="example_run")
    # todo: add pore model, extract sim params from an existing run: ConstantGapsUntilBlocked.from_seqsum_df, RollingWindowGapSamplerPerChannel.from_seqsum_df
    parser.add_argument("--n_channels", type=int, help="Number of channels", default=512)
    # parser.add_argument("--run_time", type=float, help="Time to run for (s)", default=2 ** 63 / 10 ** 9) # maximum value handled by time.sleep
    parser.add_argument("--acceleration_factor", type=float, help="Speedup factor for simulation", default=1.0)
    parser.add_argument("--min_chunk_size", type=int, help="Number of basepairs per chunk (API returns a multiple of min_chunk_size per channel)", default=200)
    parser.add_argument("--bp_per_second", type=int, help="Pore speed (number of basepairs per second (per channel))", default=450)
    parser.add_argument("--seed", type=int, help="Random seed", default=None)
    parser.add_argument("--unblock_duration", type=float, help="Duration to unblock a read (s)", default=0.1)
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing run_dir")
    parser.add_argument("--port", type=int, help="Port to use for gRPC server (0 = auto-assign)", default=0)
    parser.add_argument("--dont_start", action="store_true", help="Don't start the simulator, only start the gRPC server")
    # verbose arg
    parser.add_argument("--verbosity", type=str, help="log level of simulator", default="info")

    args = parser.parse_args(args)
    print_args(args, logger=logger)
    return args

def main():
    log_level = logging.DEBUG
    logging.getLogger(__name__).setLevel(log_level) # log level of this script (running as __main__)
    add_comprehensive_stream_handler_to_logger(None, level=log_level)
    # print_logging_levels()

    ####### Argument parsing #######
    
    if is_test_mode():
        os.chdir("server_client_cli_example")
        # args = parse_args(args=["random_reads.fasta", "example_run", "--overwrite", "--verbosity", "info", "--dont_start", "--port", "12000"])
        args = parse_args(args=["random_reads.fasta", "example_run", "--overwrite", "--verbosity", "debug", "--dont_start", "--port", "12000"])
    else:
        args = parse_args()
    
    reads_file = args.reads_file
    assert reads_file.exists(), f"reads_file '{reads_file}' does not exist"
    run_dir = args.run_dir
    n_channels = args.n_channels
    assert n_channels > 0, f"n_channels {n_channels} must be > 0"
    # run_time = args.run_time
    # assert run_time > 0, f"run_time {run_time} must be > 0"
    acceleration_factor = args.acceleration_factor
    assert acceleration_factor > 0, f"acceleration_factor {acceleration_factor} must be > 0"
    min_chunk_size = args.min_chunk_size
    assert min_chunk_size > 0, f"min_chunk_size {min_chunk_size} must be > 0"
    bp_per_second = args.bp_per_second
    assert bp_per_second > 0, f"bp_per_second {bp_per_second} must be > 0"
    seed = args.seed
    unblock_duration = args.unblock_duration
    assert unblock_duration >= 0, f"unblock_duration {unblock_duration} must be >= 0"
    overwrite = args.overwrite
    port = args.port
    assert port >= 0, f"port {port} must be >= 0"
    verbosity = args.verbosity
    dont_start = args.dont_start
    

    if run_dir.exists():
        if overwrite:
            logger.warning(f"Overwriting existing run_dir '{run_dir}'")
            shutil.rmtree(run_dir)
        else:
            raise FileExistsError(f"run_dir '{run_dir}' already exists, use --overwrite to overwrite")
    run_dir.mkdir(parents=True)
    
    logging.getLogger("simreaduntil").setLevel({"debug": logging.DEBUG, "info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR, "critical": logging.CRITICAL}[verbosity.lower()])

    ####### Setting up the simulator #######
    
    logger.info("Reading in reads. pysam index creation may take some time.")
    read_pool = ReadPoolFromFile(reads_file_or_dir = reads_file)
    read_pool = ThreadedReadPoolWrapper(read_pool, queue_size=2*n_channels)

    mk_run_dir = run_dir / "reads"
    logger.info(f"Writing basecalled reads to directory '{mk_run_dir}'")
    reads_writer = RotatingFileReadsWriter(mk_run_dir, "reads_", max_reads_per_file=4000)
    seqsum_writer = SequencingSummaryWriter(open(run_dir / "live_sequencing_summary.txt", "w"))
    comp_reads_writer = CustomCompoundReadsWriter([reads_writer, seqsum_writer], output_dir=run_dir)
    
    gap_samplers = {f"chan{channel}": ConstantGapsUntilBlocked(short_gap_length=0.4, long_gap_length=10, prob_long_gap=0.05, time_until_blocked=np.inf, read_delay=0.05) for channel in range(n_channels)}
    logger.info("Using constant gap samplers")
    sim_params = SimParams(gap_samplers=gap_samplers, bp_per_second=bp_per_second, default_unblock_duration=unblock_duration, min_chunk_size=min_chunk_size, seed=np.random.default_rng(seed))

    with reads_writer, read_pool:
        simulator = ONTSimulator(
            read_pool=read_pool, 
            reads_writer=reads_writer,
            sim_params=sim_params,
            output_dir = reads_writer.output_dir,
        )

        ####### Starting the gRPC server #######
        port, server, unique_id = launchable_device_grpc_server(simulator, port=port)
        assert port != 0, f"port {port} already in use"

        logger.info(f"Starting gRPC server on port {port}")
        with manage_grpc_server(server):
            logger.info("Started gRPC server")
            
            def stop_server(*args, **kwargs):
                if simulator.stop():
                    logger.info("Stopped simulation")
                
            with set_signal_handler(signal_type=signal.SIGINT, handler=stop_server): # catch keyboard interrupt (Ctrl+C)
                if not dont_start:
                    logger.info("Starting the simulation")
                    simulator.start(acceleration_factor=acceleration_factor, log_interval=100)
                else:
                    logger.info("Not starting the simulation, must be started manually (via a gRPC call), or remove the --dont_start flag")
                signal.pause() # wait for keyboard interrupt, only for Linux, alternatively run a while loop with time.sleep(1)
            
        write_simulator_stats([simulator], output_dir=simulator.mk_run_dir)

    # todo: possibly remove since the same as live sequencing summary
    seqsum_filename = run_dir / "sequencing_summary.txt"
    logger.info(f"Writing sequencing summary file '{seqsum_filename}'")
    convert_simfasta_dir_to_seqsum(comp_reads_writer.output_dir, seqsummary_filename=seqsum_filename)
    logger.info("Wrote sequencing summary file")

    logger.info("Done with simulation")


if __name__ == "__main__":
    main()
