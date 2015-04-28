import spotipy
import simplejson as json
import pprint as pp
import sys
import collections
import time
import datetime
import cPickle as pickle
import os
import atexit

silent = False
search_limit = 50
max_albums = 5000
max_albums = 100000
max_tracks = 1

spotify = spotipy.Spotify()

artist_names = set()
fresh_album_ids = set()
older_artists = set()
yesterdays_rank = {}

def fetch_albums(albums):
    ret_albums = []
    max_batch = 20
    ids = []
    for album in albums:
        ids.append(album['id'])

    for i in xrange(0, len(ids), max_batch):
        nids = ids[i:i + max_batch]

        retries = 5
        while retries > 0:
            try:
                results = spotify.albums(nids)
                albums = results['albums']
                ret_albums.extend(albums)
                break
            except:
                raise
                if True:
                    retries -=1
                    if not silent:
                        print 'retrying ...', retries
                    time.sleep(1)
    return ret_albums

def fetch_artists(ids):
    ret_artists = []
    max_batch = 20

    for i in xrange(0, len(ids), max_batch):
        nids = ids[i:i + max_batch]

        retries = 5
        while retries > 0:
            try:
                results = spotify.artists(nids)
                artists = results['artists']
                ret_artists.extend(artists)
                break
            except:
                raise
                if True:
                    retries -=1
                    if not silent:
                        print 'retrying ...', retries
                    time.sleep(1)
    return ret_artists
    
    
def get_new_albums():
    albums = []
    results = spotify.search(q='tag:new', type='album', limit=search_limit)

    albums.extend( fetch_albums(results['albums']['items']) )

    while results['albums']['next']:
        if not silent:
            print len(albums)
        retries = 5
        while retries > 0:
            try:
                results = spotify.next(results['albums'])
                break
            except:
                if True:
                    retries -=1
                    if not silent:
                        print 'retrying ...', retries
                    time.sleep(1)
        
        albums.extend( fetch_albums(results['albums']['items']) )
        if len(albums) > max_albums:
            break

    if not silent:
        print 'total albums', len(albums)

    for album in albums:
        fresh_album_ids.add( album['id'] )

    return albums

def is_compilation(album):
    various_artists = '0LyfQWJT6nXafLPZqxe9Of'

    if album['album_type'] == 'compilation':
        return True

    for artist in album['artists']:
        if artist['id'] == various_artists:
            if not silent:
                print 'skipped', artist['id']
            return True
    return False

def artist_has_older_album(aid):
    if aid in older_artists:
        return True
    else:
        results = spotify.artist_albums(aid, limit=50, album_type='single,album')
        tot = results['total']
        for album in results['items']:
            if album['id'] not in fresh_album_ids:
                older_artists.add(aid)
                return True
    return False

def process_albums1(albums):
    out_albums = []
    for album in albums:
        if is_compilation(album):
            continue
        aname = album['artists'][0]['name']

        album['days_on_chart'] = get_days_on_chart(album)
        if album['days_on_chart'] > 14:
            continue
        # dedup by artist names
        if aname in artist_names:
            continue
        artist_names.add(aname)

        out_albums.append(album)
    return out_albums

def process_albums2(albums):
    out_albums = []
    for i, album in enumerate(albums):
        if not silent:
            print i, 'of', len(albums), 'found', len(out_albums)
        if artist_has_older_album(album['artists'][0]['id']):
            continue
        out_albums.append(album)
    return out_albums

def get_artist_info(uris):
    page_size = 50

    map = {}
    for start in xrange(0, len(uris), page_size):
        turis = uris[start:start + page_size]
        results = spotify.artists(turis)
        for artist in results['artists']:
            map[ artist['uri'] ] = artist
    return map

    

def process_albums4(albums):
    # get the artist followers for the remaining artists

    uris = []
    for album in albums:
        uris.append(album['artist_uri'])

    fmap = get_artist_info(uris)

    for album in albums:
        ainfo = fmap[ album['artist_uri'] ]
        album['artist_followers'] = ainfo['followers']['total']
        album['artist_popularity'] = ainfo['popularity']
        if 'images' in ainfo and len(ainfo['images']) > 0:
            album['artist_image'] = ainfo['images'][0]['url']

    albums.sort(key=lambda a:a['popularity'], reverse=True)
    albums.sort(key=lambda a:a['artist_popularity'], reverse=True)
    albums.sort(key=lambda a:a['artist_followers'], reverse=True)

    max_followers = albums[0]['artist_followers']
    for album in albums:
        nfollows = album['artist_followers'] * 100.0 / max_followers
        album['nartist_followers'] = nfollows
        score = (10 * nfollows + album['popularity'] + album['artist_popularity']) / 12.
        album['score'] = score

    albums.sort(key=lambda a:a['score'], reverse=True)

    for rank, album in enumerate(albums):
        print rank, album['score']
        album['rank'] = rank
        if album['id'] in yesterdays_rank:
            yrank = yesterdays_rank[ album['id'] ]
            album['prev_rank'] = yrank
            if rank < yrank:
                album['delta_rank'] = 'up'
            elif rank > yrank:
                album['delta_rank'] = 'down'
            else:
                album['delta_rank'] = 'same'
        else:
            album['prev_rank'] = -1
            album['delta_rank'] = 'up'



    return albums


def cache_save():
    f = open('cache.pkl', 'w')
    pickle.dump(older_artists, f, -1)
    f.close()
    if not silent:
        print 'cached', len(older_artists), 'artists'

def cache_load():
    obj = set()
    if os.path.exists('cache.pkl'):
        f = open('cache.pkl')
        obj = pickle.load(f)
        f.close()
        if not silent:
            print 'loaded', len(obj), 'artists'
    atexit.register(cache_save)
    return obj


def filter_tracks(album):
    out = []
    for track in album['tracks']['items'][:max_tracks]:
        ttrack = {
            'id': track['id'],
            'preview_url': track['preview_url'],
            'name': track['name']
        }
        out.append(ttrack)
    return out

def get_days_on_chart(album):
    now = datetime.date.today()
    try:
        rel = datetime.datetime.strptime(album['release_date'], '%Y-%m-%d').date()
        dt = now - rel
        print now, rel, dt, dt.days
        return dt.days
    except:
        return 1000
    

def process_albums3(albums):
    albums.sort(key=lambda a:a['popularity'], reverse=True)
    for album in albums:
        album['tracks'] = filter_tracks(album)

        del album['available_markets']
        del album['copyrights']
        del album['external_ids']
        del album['external_urls']
        del album['genres']
        del album['type']

        album['artist_name'] = album['artists'][0]['name']
        album['artist_uri'] = album['artists'][0]['uri']
        del album['artists']

        image_large = None
        image_med = None
        images = album['images']


        if len(images) > 0:
            for image in images:
                if image_large == None and image['width'] > 400:
                    image_large = image['url']
                if image_med == None and image['width'] <= 400 and \
                        image['width'] >= 300:
                    image_med = image['url']

            if image_large == None:
                image_large = images[0]['url']
            if image_med == None:
                image_med = image_large
            image_small = images[-1]['url']

        del album['images']
        album['image_large'] = image_large
        album['image_med'] = image_med
        album['image_small'] = image_small

        del album['release_date_precision']
        del album['href']
    return albums


def make_date_hist(albums):
    hist = collections.defaultdict(int)
    for album in albums:
        hist[album['release_date']] += 1
    return hist

        
def save(json_blob, name):
    js = json.dumps(json_blob)
    f = open(name, 'w')
    print >>f, js
    f.close()

def load_yesterdays_rank():
    yranks = {}
    path = 'yesterday.js'
    if os.path.exists(path):
        f = open(path)
        js = f.read()
        f.close()
        obj = json.loads(js)
        for album in obj['albums']:
            yranks[ album['id'] ] = album['rank']

    if not silent:
        print 'loaded', len(yranks), 'albums from yesterday'
    return yranks
        

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--silent':
        silent = True
    older_artists = cache_load()
    yesterdays_rank = load_yesterdays_rank()
    albums = get_new_albums()
    new_albums = len(albums)
    if not silent:
        print 'new albums',len(albums)

    all_hist = make_date_hist(albums)

    albums = process_albums1(albums)
    albums = process_albums2(albums)
    albums = process_albums3(albums)
    albums = process_albums4(albums)

    fresh_hist = make_date_hist(albums)

    json_blob = {
        'albums': albums,
        'version': '1.0',
        'new_albums': new_albums,
        'date': str(datetime.datetime.now()),
        'release_date_hist': all_hist,
        'fresh_date_hist': fresh_hist,
    }
    save(json_blob,name='new_releases.js')
    json_blob['albums'] = json_blob['albums'][:40]
    save(json_blob,name='quick_releases.js')

