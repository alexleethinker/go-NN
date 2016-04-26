#!/usr/bin/python
import numpy as np
import random
import os

class RandomizingWriter:
    def __init__(self, out_dir, names, shapes, dtypes, Nperfile, buffer_len):
        assert buffer_len >= Nperfile
        assert len(names) == len(shapes) == len(dtypes)
        self.out_dir = out_dir
        self.names = names
        self.shapes = shapes
        self.dtypes = dtypes
        self.Nperfile = Nperfile
        self.buffer_len = buffer_len
        self.examples = []
        self.filenum = 0

    def push_example(self, example):
        assert len(example) == len(self.names)
        for i in xrange(len(example)):
            assert example[i].dtype == self.dtypes[i]
        self.examples.append(example)
        if len(self.examples) >= self.buffer_len:
            self.write_npz_file()

    def drain(self):
        print "NPZ.RandomizingWriter: draining..."
        while len(self.examples) >= self.Nperfile:
            self.write_npz_file()
        print "NPZ.RandomizingWriter: finished draining. %d examples left unwritten." % len(self.examples)

    def write_npz_file(self):
        assert len(self.examples) >= self.Nperfile

        # put Nperfile random examples at the end of the list
        for i in xrange(self.Nperfile):
            a = len(self.examples) - i - 1
            if a > 0:
              b = random.randint(0, a-1)
              self.examples[a], self.examples[b] = self.examples[b], self.examples[a]

        # pop Nperfile examples off the end of the list
        # put each component into a separate numpy batch array
        save_dict = {}
        for c in xrange(len(self.names)):
            batch_shape = (self.Nperfile,) + self.shapes[c]
            batch = np.empty(batch_shape, dtype=self.dtypes[c])
            for i in xrange(self.Nperfile):
                batch[i,:] = self.examples[-1-i][c]
            save_dict[self.names[c]] = batch

        del self.examples[-self.Nperfile:]

        filename = os.path.join(self.out_dir, "examples.%d.%d" % (self.Nperfile, self.filenum))
        #print "NPZ.RandomizingWriter: writing", filename
        np.savez_compressed(filename, **save_dict)
        self.filenum += 1


def read_npz(filename, names):
    npz = np.load(filename)
    ret = dict((name, npz[name]) for name in names)
    npz.close()
    return ret

class Loader:
    def __init__(self, npz_dir):
        self.filename_queue = [os.path.join(npz_dir, f) for f in os.listdir(npz_dir)]
    def has_more(self):
        return len(self.filename_queue) > 0
    def next_minibatch(self, names):
        return read_npz(self.filename_queue.pop(), names)


class RandomizingLoader:
    def __init__(self, npz_dir, minibatch_size):
        self.filename_queue = []
        self.npz_dir = npz_dir
        self.minibatch_size = minibatch_size
        self.saved_examples = None
        self.num_saved_examples = 0

    def load_more_examples(self, names):
        #print "loading more examples..."
        if not self.filename_queue:
            self.filename_queue = [os.path.join(self.npz_dir, f) for f in os.listdir(self.npz_dir)]
            random.shuffle(self.filename_queue)
            print "RandomizingLoader: built new filename queue with length", len(self.filename_queue)
        examples = read_npz(self.filename_queue.pop(), names)
        if self.saved_examples == None:
            self.saved_examples = examples
        else:
            for name in names:
                self.saved_examples[name] = np.concatenate((self.saved_examples[name], examples[name]))
        self.num_saved_examples = self.saved_examples[names[0]].shape[0]
        #print "now num_saved_examples =", self.num_saved_examples

    def next_minibatch(self, names):
        #print "asked for minibatch of size %d when num_saved_examples = %d" % (self.minibatch_size, self.num_saved_examples)
        while self.num_saved_examples < self.minibatch_size:
            self.load_more_examples(names)
        batch = {}
        for name in names:
            batch[name] = self.saved_examples[name][0:self.minibatch_size,:]
            self.saved_examples[name] = self.saved_examples[name][self.minibatch_size:,:]
        self.num_saved_examples -= self.minibatch_size
        #print "after returning minibatch, num_saved_examples = %d" % self.num_saved_examples
        return batch


"""
class RandomizingLoader:
    def __init__(self, npz_dir):
        self.filename_queue = None
        self.npz_dir = npz_dir
    def next_minibatch(self, names):
        if not self.filename_queue:
            self.filename_queue = [os.path.join(self.npz_dir, f) for f in os.listdir(self.npz_dir)]
            random.shuffle(self.filename_queue)
            print "RandomizingLoader: built new filename queue with length", len(self.filename_queue)
        return read_npz(self.filename_queue.pop(), names)


class GroupingRandomizingLoader:
    def __init__(self, npz_dir, Ngroup):
        self.filename_queue = []
        self.npz_dir = npz_dir
        self.Ngroup = Ngroup
    def next_minibatch(self, names):
        if len(self.filename_queue) < self.Ngroup:
            self.filename_queue = [os.path.join(self.npz_dir, f) for f in os.listdir(self.npz_dir)]
            random.shuffle(self.filename_queue)
            print "GroupingRandomizingLoader: built new filename queue with length", len(self.filename_queue)
        components = [read_npz(self.filename_queue.pop(), ('feature_planes', 'moves')) for i in xrange(self.Ngroup)]
        Nperfile = components[0][0].shape[0]
        N = components[0][0].shape[1]
        Nfeat = components[0][0].shape[3]
        grouped_features = np.empty((Nperfile * self.Ngroup, N, N, Nfeat), dtype=np.int8)
        grouped_moves = np.empty((Nperfile * self.Ngroup, 2), dtype=np.int8)
        for i in xrange(self.Ngroup):
            start = i * Nperfile
            end = (i+1) * Nperfile
            grouped_features[start:end,:,:,:], grouped_moves[start:end,:] = components[i]
        return grouped_features, grouped_moves

class SplittingRandomizingLoader:
    def __init__(self, npz_dir, Nsplit):
        self.filename_queue = []
        self.npz_dir = npz_dir
        self.Nsplit = Nsplit
        self.Nsaved = 0
    def next_minibatch(self, names):
        if not self.filename_queue:
            self.filename_queue = [os.path.join(self.npz_dir, f) for f in os.listdir(self.npz_dir)]
            random.shuffle(self.filename_queue)
            print "RandomizingNpzMinibatcher: built new filename queue with length", len(self.filename_queue)
        if self.Nsaved == 0:
            self.saved_batches = dict((name, []) for name in names)        
            big_batch = read_npz(self.filename_queue.pop(), names)
            for n,name in enumerate(names):
                Nbig = big_batch[n].shape[0]
                assert Nbig % self.Nsplit == 0
                for i in range(self.Nsplit):
                    start = i*Nbig/self.Nsplit
                    end = (i+1)*Nbig/self.Nsplit
                    self.saved_batches[name].append(big_batch[n][start:end,:])
            self.Nsaved += self.Nsplit
        self.Nsaved -= 1
        return tuple(self.saved_batches[name].pop() for name in names)
"""




if __name__ == '__main__':
    writer = RandomizingNpzWriter('/tmp/npz_writer',
            names=['some_ints', 'some_floats'],
            shapes=[(2,2), (2,)],
            dtypes=[np.int32, np.float32],
            Nperfile=2, buffer_len=4)

    writer.push_example((1*np.ones((2,2),dtype=np.int32), 1*np.array([1.0, 1.0], dtype=np.float32)))
    writer.push_example((2*np.ones((2,2),dtype=np.int32), 2*np.array([1.0, 1.0], dtype=np.float32)))
    writer.push_example((3*np.ones((2,2),dtype=np.int32), 3*np.array([1.0, 1.0], dtype=np.float32)))
    writer.push_example((4*np.ones((2,2),dtype=np.int32), 4*np.array([1.0, 1.0], dtype=np.float32)))
    writer.push_example((5*np.ones((2,2),dtype=np.int32), 5*np.array([1.0, 1.0], dtype=np.float32)))
    writer.push_example((6*np.ones((2,2),dtype=np.int32), 6*np.array([1.0, 1.0], dtype=np.float32)))
    writer.push_example((7*np.ones((2,2),dtype=np.int32), 7*np.array([1.0, 1.0], dtype=np.float32)))
    writer.push_example((8*np.ones((2,2),dtype=np.int32), 8*np.array([1.0, 1.0], dtype=np.float32)))
    writer.drain()






