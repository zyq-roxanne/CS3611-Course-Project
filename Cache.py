import datetime

class Cache:
    def __init__(self, size = 10):
        self.cache = dict()
        self.max_cache_size = size

    def __contains__(self, key):
        '''
        If key is contained in cache

        Parameters
        ----------
        key : searched key

        Returns
        -------
        flag : True or False
        '''
        return key in self.cache
    
    def update(self, key, value):
        '''
        Add key and value to cache

        Parameters
        ----------
        key : key
        value : valuelist
        '''
        if key not in self.cache and len(self.cache) >= self.max_cache_size:
            self.pop_out()
        self.cache[key] = {
            'lastCached': datetime.datetime.now(),
            'value': value
        }

    def pop_out(self):
        '''
        Pop the oldest file if the cache is full
        '''
        oldest_item = None
        for item in self.cache:
            if oldest_item is None:
                oldest_item = item
            elif self.cache[item]['lastCached'] < self.cache[oldest_item]['lastCached']:
                oldest_item = item
        self.cache.pop(oldest_item)

    def get(self, key):
        '''
        Return value
        '''
        return self.cache[key]['value']
    


    @property
    def size(self):
        return len(self.cache)

# cache = Cache()
# cache.update('1', 'Hello')
# print(cache.get('1'))