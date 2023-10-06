#!/usr/bin/env bash 

# it seems 2 CPUs are fine based on condor log average resource usage
##CONDOR request_cpus=2
# takes about 8GB of memory
##CONDOR request_memory=32000
##CONDOR request_disk=100G
##CONDOR log = /home/mmordig/joblogs/job-$(ClusterId)-$(ProcId).log
##CONDOR output = /home/mmordig/joblogs/job-$(ClusterId)-$(ProcId).out
##CONDOR error = /home/mmordig/joblogs/job-$(ClusterId)-$(ProcId).err

# launch_condor_job 20 --- ~/ont_project_all/ont_project/usecases/enrich_usecase_submission.sh

echo "Content of job ad file $_CONDOR_JOB_AD:"; cat "$_CONDOR_JOB_AD"
echo "Starting job with args: " "$@"
echo "Cwd: $(pwd)"
source ~/.bashrc

cd ~/ont_project_all/ont_project/

source ~/ont_project_all/ont_project_venv/bin/activate
export PATH=~/ont_project_all/tools/bin:$PATH && which minimap2

set -ex

cd runs/enrich_usecase
rm -rf full_genome_run_sampler_per_window
mkdir full_genome_run_sampler_per_window
cd full_genome_run_sampler_per_window
ln -s ../data .
ln -s ../configs/full_genome_run/sampler_per_window configs
python ~/ont_project_all/ont_project/usecases/enrich_usecase.py

# symlink job output files to directory
# parse stderr from job ad file
# Err = "/home/mmordig/joblogs/job-13951206-0.err"
if [ -n "$_CONDOR_JOB_AD" ]; then
    grep -oP '(?<=Err = ").*(?=")' "$_CONDOR_JOB_AD" | xargs -I {} ln -s {} .
    grep -oP '(?<=Out = ").*(?=")' "$_CONDOR_JOB_AD" | xargs -I {} ln -s {} .
    grep -oP '(?<=Log = ").*(?=")' "$_CONDOR_JOB_AD" | xargs -I {} ln -s {} .
fi

echo "Done with job, pwd $(pwd)"
