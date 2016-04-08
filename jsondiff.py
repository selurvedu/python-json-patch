'''
The MIT License (MIT)

Copyright (c) 2014 Ilya Volkov

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

import sys

__all__ = ["make",]

if sys.version_info[0] >= 3:
    _range = range
    _str = str
    _viewkeys = dict.keys
else:
    _range = xrange
    _str = unicode
    if sys.version_info[1] >= 7:
        _viewkeys = dict.viewkeys
    else:
        _viewkeys = lambda x: set(dict.keys(x))

_ST_ADD    = 0
_ST_REMOVE = 1

class _compare_info(object):

    def __init__(self):
        self.index_storage = [{}, {}]
        self.index_storage2 = [[], []]
        self.__root = root = []
        root[:] = [root, root, None]

    def store_index(self, value, index, st):
        try:
            storage = self.index_storage[st]
            stored = storage.get(value)
            if stored == None:
                storage[value] = [index]
            else:
                storage[value].append(index)
        except TypeError:
            self.index_storage2[st].append((value, index))

    def take_index(self, value, st):
        try:
            stored = self.index_storage[st].get(value)
            if stored:
                return stored.pop()
        except TypeError:
            storage = self.index_storage2[st]
            for i in range(len(storage)-1, -1, -1):
                if storage[i][0] == value:
                    return storage.pop(i)[1]

    def insert(self, op):
        root = self.__root
        last = root[0]
        last[1] = root[0] = [last, root, op]
        return root[0]

    def remove(self, index):
        link_prev, link_next, _ = index
        link_prev[1] = link_next
        link_next[0] = link_prev
        index[:] = []

    def iter_from(self, start):
        root = self.__root
        curr = start[1]
        while curr is not root:
            yield curr[2]
            curr = curr[1]

    def __iter__(self):
        root = self.__root
        curr = root[1]
        while curr is not root:
            yield curr[2]
            curr = curr[1]

    def execute(self):
        root = self.__root
        curr = root[1]
        while curr is not root:
            if curr[1] is not root:
                op_first, op_second = curr[2], curr[1][2]
                if op_first.key == op_second.key and \
                        op_first.path == op_second.path and \
                        type(op_first) == _op_remove and \
                        type(op_second) == _op_add:
                    yield _op_replace(op_second.path, op_second.key, op_second.value).get()
                    curr = curr[1][1]
                    continue
            yield curr[2].get()
            curr = curr[1]

class _op_base(object):
    def __init__(self, path, key, value):
        self.path  = path
        self.key   = key
        self.value = value

    def __repr__(self):
        return _str(self.get())

class _op_add(_op_base):
    def _on_undo_remove(self, path, key):
        if self.path == path:
            if self.key > key:
                self.key += 1
            else:
                key += 1
        return key

    def _on_undo_add(self, path, key):
        if self.path == path:
            if self.key > key:
                self.key -= 1
            else:
                key += 1
        return key

    def get(self):
        return {'op': 'add', 'path': _path_join(self.path, self.key), 'value': self.value}

class _op_remove(_op_base):
    def _on_undo_remove(self, path, key):
        if self.path == path:
            if self.key >= key:
                self.key += 1
            else:
                key -= 1
        return key

    def _on_undo_add(self, path, key):
        if self.path == path:
            if self.key > key:
                self.key -= 1
            else:
                key -= 1
        return key

    def get(self):
        return {'op': 'remove', 'path': _path_join(self.path, self.key)}

class _op_replace(_op_base):
    def _on_undo_remove(self, path, key):
        return key

    def _on_undo_add(self, path, key):
        return key

    def get(self):
        return {'op': 'replace', 'path': _path_join(self.path, self.key), 'value': self.value}

class _op_move(object):
    def __init__(self, oldpath, oldkey, path, key):
        self.oldpath = oldpath
        self.oldkey  = oldkey
        self.path    = path
        self.key     = key

    def _on_undo_remove(self, path, key):
        if self.oldpath == path:
            if self.oldkey >= key:
                self.oldkey += 1
            else:
                key -= 1
        if self.path == path:
            if self.key > key:
                self.key += 1
            else:
                key += 1
        return key

    def _on_undo_add(self, path, key):
        if self.oldpath == path:
            if self.oldkey > key:
                self.oldkey -= 1
            else:
                key -= 1
        if self.path == path:
            if self.key > key:
                self.key -= 1
            else:
                key += 1
        return key

    def get(self):
        return {'op': 'move', 'path': _path_join(self.path, self.key), 'from': _path_join(self.oldpath, self.oldkey)}

    def __repr__(self):
        return _str(self.get())

def _path_join(path, key):
    if key != None:
        return path + '/' + _str(key).replace('~', '~0').replace('/', '~1')
    return path

def _item_added(path, key, info, item):
    index = info.take_index(item, _ST_REMOVE)
    if index != None:
        op = index[2]
        if type(op.key) == int:
            for v in info.iter_from(index):
                op.key = v._on_undo_remove(op.path, op.key)
        info.remove(index)
        if op.path != path or op.key != key:
            new_op = _op_move(op.path, op.key, path, key)
            info.insert(new_op)
    else:
        new_op = _op_add(path, key, item)
        new_index = info.insert(new_op)
        info.store_index(item, new_index, _ST_ADD)

def _item_removed(path, key, info, item):
    new_op = _op_remove(path, key, item)
    index = info.take_index(item, _ST_ADD)
    new_index = info.insert(new_op)
    if index != None:
        op = index[2]
        if type(op.key) == int:
            for v in info.iter_from(index):
                op.key = v._on_undo_add(op.path, op.key)
        info.remove(index)
        if new_op.path != op.path or new_op.key != op.key:
            new_op = _op_move(new_op.path, new_op.key, op.path, op.key)
            new_index[2] = new_op
        else:
            info.remove(new_index)
    else:
        info.store_index(item, new_index, _ST_REMOVE)

def _item_replaced(path, key, info, item):
    info.insert(_op_replace(path, key, item))

def _compare_dicts(path, info, src, dst):
    src_keys = _viewkeys(src)
    dst_keys = _viewkeys(dst)
    added_keys = dst_keys - src_keys
    removed_keys = src_keys - dst_keys
    for key in removed_keys:
        _item_removed(path, _str(key), info, src[key])
    for key in added_keys:
        _item_added(path, _str(key), info, dst[key])
    for key in src_keys & dst_keys:
        _compare_values(path, key, info, src[key], dst[key])

def _compare_lists(path, info, src, dst):
    len_src, len_dst = len(src), len(dst)
    max_len = max(len_src, len_dst)
    min_len = min(len_src, len_dst)
    for key in _range(max_len):
        if key < min_len:
            old, new = src[key], dst[key]
            if old == new:
                continue
            _item_removed(path, key, info, old)
            _item_added(path, key, info, new)
        elif len_src > len_dst:
            _item_removed(path, len_dst, info, src[key])
        else:
            _item_added(path, key, info, dst[key])

def _compare_values(path, key, info, src, dst):
    if src == dst:
        return
    elif isinstance(src, dict) and \
            isinstance(dst, dict):
        _compare_dicts(_path_join(path, key), info, src, dst)
    elif isinstance(src, list) and \
            isinstance(dst, list):
        _compare_lists(_path_join(path, key), info, src, dst)
    else:
        _item_replaced(path, key, info, dst)

def make(src, dst, **kwargs):
    info = _compare_info()
    _compare_values('', None, info, src, dst)
    return [op for op in info.execute()]
