#!/usr/bin/env bash

# Run this script fron the `ont_project` root directory
# Installs minimap2 and NanoSim

# set -e

on_exit () {
    echo "This script has exited with an error"
    exit 1
}
trap on_exit ERR

####################################################
# read parameters

tools_dir=~/ont_project_all/tools
conda_or_mamba="conda" # very slow
# if mamba is available, use mamba
which mamba && conda_or_mamba="mamba"
echo "Using $conda_or_mamba for conda environment creation"

usage() {
    echo "Usage: $0 [-h] [-e <env>] [-t <tools_dir>]"
    echo "  -h  Help. Display this message and quit."
    echo "  -t  tools directory"
    echo "  -f  force installation; skipped if nanosim environment installed"
    exit 1
}

optspec="e:t:h"
while getopts "$optspec" optchar
do
    case "${optchar}" in
        h)
            usage
            ;;
        t)
            tools_dir=${OPTARG}
           ;;
    esac
done


echo "The current base directory to install minimap to is: $tools_dir"
# echo "(press Return to confirm or enter a new path)"

# read new_value

# if [ ! -z "$new_value" ]
# then
#     tools_dir=${new_value}
#     echo "Updated path to: $tools_dir"
# fi

# check we are in the right directory by checking for a directory "external"
[ -d "external" ] || (echo "Error: not in the right directory. Run this script from the ont_project root directory containing the external directory"; exit 1)


# ####################################################

####################################################
# install minimap2
# see https://github.com/lh3/minimap2/releases

function install_minimap() {
    echo "Installing minimap2"
    # check if is linux
    if [[ "$OSTYPE" != "linux-gnu"* ]]; then
        echo "Compiling minimap2 from source"
        curl -L https://github.com/lh3/minimap2/releases/download/v2.26/minimap2-2.26.tar.bz2 | tar -jxvf -
        cd minimap2-2.26
        make arm_neon=1 aarch64=1 #changed by AG
    else
        echo "Downloading precompiled minimap2 binary for linux"
        curl -L https://github.com/lh3/minimap2/releases/download/v2.26/minimap2-2.26_x64-linux.tar.bz2 | tar -jxvf -
        cd minimap2-2.26_x64-linux
    fi

    rm -f "$tools_dir/bin/minimap2" # delete potentially existing symlink from previous run
    ln -s "$(readlink -f minimap2)" "$tools_dir/bin/minimap2"
    # which minimap2
}

# install only if minimap2 not available
mkdir -p "$tools_dir/downloads"
mkdir -p "$tools_dir/bin"

which minimap2 || (cd "$tools_dir/downloads"; install_minimap)

echo "Installed minimap2 to location: $(which minimap2)"
echo "Make sure to add this to your PATH variable, e.g."
echo "export \"PATH=$tools_dir/bin:\$PATH\""

# exit 0

####################################################
# install NanoSim conda env
# Since NanoSim comes with precomputed models (saved in numpy format) and we had version incompatibilities, 
# we use a separate environment for NanoSim. This works because NanoSim reads are simulated in a 
# separate process independent of the simulator.

echo "Installing conda environment for NanoSim using $conda_or_mamba"
#AG modified below to activate the pyenv86 alias from AG_py3.7.sh
CONDA_SUBDIR=osx-64
$conda_or_mamba create --yes --name nanosim
source activate nanosim
$conda_or_mamba config --env --set subdir osx-64

export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv86 init -)"
pyenv shell pyenv86

# conda init bash does not work for me, so do: 
# . "/Users/maximilianmordig/software/anaconda/etc/profile.d/conda.sh"
#AG has placed the tar.bz2 files, including the old version of scikit-learn & htseq & genometools-genometools, in the ont_project directory to get this to run
$conda_or_mamba install -n nanosim --yes --file external/ont_nanosim/requirements.txt -c conda-forge -c bioconda
$conda_or_mamba run -n nanosim python -c "import HTSeq; print(HTSeq.__version__)"
# e.g. conda config --set auto_activate_base false

echo "Installed conda environment for NanoSim"

echo "Installing genometools-genometools using Homebrew"

echo "Successfully installed all dependencies"

echo "Installed conda environment for NanoSim"


echo "Successfully installed all dependencies"
