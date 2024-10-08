    
from pathlib import Path
import shutil
import dill
from simreaduntil.shared_utils.utils import get_file_content
from simreaduntil.simulator.readswriter import ArrayReadsWriter, CompoundReadsWriter, RotatingFileReadsWriter, SingleFileReadsWriter, ThreadedReadsWriterWrapper
from Bio import SeqIO
from Bio.Seq import Seq

def test_SingleFileReadsWriter(tmp_path):
    
    for (writer_wrapper, test_picklable) in [(lambda x: x, True), (ThreadedReadsWriterWrapper, False)]:
        filename = tmp_path / "reads1.txt"
        with open(filename, "w") as fh:
            reads_writer = SingleFileReadsWriter(fh, prefix="Pref:")
            reads_writer = writer_wrapper(reads_writer)
            reads_writer.write_read(SeqIO.SeqRecord(Seq("AACCGTT"), id="read1"))
            reads_writer.write_read(SeqIO.SeqRecord(Seq("GGGGCCAA"), id="read2"))
            print(reads_writer)
        
            reads_writer.finish()
        
        expected_content = ">Pref:read1 <unknown description>\nAACCGTT\n>Pref:read2 <unknown description>\nGGGGCCAA\n"
        assert get_file_content(filename) == expected_content
        if test_picklable:
            obj = dill.loads(dill.dumps(reads_writer))
            assert obj.fh is None
            # check file not overwritten
            assert get_file_content(filename) == expected_content
        
    
def test_ArrayReadsWriter():
    reads_writer = ArrayReadsWriter()
    reads_writer.write_read(SeqIO.SeqRecord(Seq("AACCGTT"), id="read1"))
    reads_writer.write_read(SeqIO.SeqRecord(Seq("GGGGCCAA"), id="read2"))
    assert reads_writer.reads ==  [("read1", Seq("AACCGTT"), "<unknown description>"), ("read2", Seq("GGGGCCAA"), "<unknown description>")]
    str(reads_writer)
    str(reads_writer.extended_repr())
    
    dill.loads(dill.dumps(reads_writer))
    
def test_CompoundReadsWriter():
    reads_writer1 = ArrayReadsWriter()
    reads_writer2 = ArrayReadsWriter()
    with CompoundReadsWriter([reads_writer1, reads_writer2]) as reads_writer:
        reads_writer.write_read(SeqIO.SeqRecord(Seq("AACCGTT"), id="read1"))
        reads_writer.write_read(SeqIO.SeqRecord(Seq("GGGGCCAA"), id="read2"))
        
        repr(reads_writer)
    
    assert reads_writer1.reads ==  [("read1", Seq("AACCGTT"), "<unknown description>"), ("read2", Seq("GGGGCCAA"), "<unknown description>")]
    assert reads_writer2.reads ==  [("read1", Seq("AACCGTT"), "<unknown description>"), ("read2", Seq("GGGGCCAA"), "<unknown description>")]
    
def test_RotatingFileReadsWriter(tmp_path):
    def nb_files_in_dir(path):
        return sum(1 for _ in Path(path).iterdir())
    
    # target_dir = "test123"
    target_dir = tmp_path / "reads_writer"
    with RotatingFileReadsWriter(target_dir, "reads_", max_reads_per_file=3) as reads_writer:
        assert nb_files_in_dir(target_dir) == 0
        reads_writer.write_read(SeqIO.SeqRecord(Seq("AACCGTT"), id="read1"))
        assert nb_files_in_dir(target_dir) == 0
        reads_writer.write_read(SeqIO.SeqRecord(Seq("AACCGTT"), id="read2"))
        assert nb_files_in_dir(target_dir) == 0
        reads_writer.write_read(SeqIO.SeqRecord(Seq("AACCGTT"), id="read3"))
        assert nb_files_in_dir(target_dir) == 1
        reads_writer.write_read(SeqIO.SeqRecord(Seq("AACCGTT"), id="read4"))
        assert nb_files_in_dir(target_dir) == 1
    assert nb_files_in_dir(target_dir) == 2
    print(reads_writer)
    
    expected_content = ">read1 <unknown description>\nAACCGTT\n>read2 <unknown description>\nAACCGTT\n>read3 <unknown description>\nAACCGTT\n>read4 <unknown description>\nAACCGTT\n"
    assert get_file_content(target_dir / "reads_0.fasta") + get_file_content(target_dir / "reads_1.fasta") == expected_content
    dill.loads(dill.dumps(reads_writer))
    # check file not overwritten
    assert get_file_content(target_dir / "reads_0.fasta") + get_file_content(target_dir / "reads_1.fasta") == expected_content
    