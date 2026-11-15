import math
import os
from time import monotonic, sleep

import pytest
from fastapi.testclient import TestClient

from spacegit_edge.main import make_app


pytestmark = pytest.mark.skipif(os.environ.get('SPACEGIT_TEST_SURFACES')!='1', reason='Requires the Open3D worker')


def scan_bytes(count=500):
    header = ('ply\nformat ascii 1.0\n' + f'element vertex {count}\n'
              'property float x\nproperty float y\nproperty float z\nend_header\n')
    points = []
    for index in range(count):
        y = 1-2*(index+.5)/count
        r, angle = math.sqrt(1-y*y), index*math.pi*(3-math.sqrt(5))
        points.append(f'{r*math.cos(angle)} {y} {r*math.sin(angle)}\n')
    return (header+''.join(points)).encode()


def wait(client, path, headers):
    deadline = monotonic()+30
    while monotonic()<deadline:
        response = client.get(path, headers=headers)
        assert response.status_code==200
        job = response.json()
        if job['status'] not in ('queued', 'running'):
            return job
        sleep(.1)
    pytest.fail('The surface job did not finish.')


def test_local_smoothing_preview_and_cancel(tmp_path):
    token = 'test-surface-edge-token-for-local-tests'
    headers = {'Authorization': 'Bearer '+token}
    base = '/api/v1/surfaces'
    scan = scan_bytes()
    with TestClient(make_app(path=tmp_path/'edge.sqlite3', mode='demo', token=token)) as client:
        assert client.get(base+'/jobs/invalid').status_code==401
        result = client.post(base+'/inputs', content=scan, headers={**headers, 'Content-Type':'application/octet-stream'})
        assert result.status_code==201
        source = result.json()['source']

        def submit(action, **extra):
            response = client.post(base+'/jobs', headers=headers,
                                   json={'source':source, 'action':action, **extra})
            assert response.status_code==202, response.text
            return base+'/jobs/'+response.json()['id']

        analysis = wait(client, submit('analyse'), headers)
        assert analysis['status']=='complete' and analysis['reports']['1']['recommended_depth']==8
        first_path = submit('reconstruct', settings={'depth':7})
        first = wait(client, first_path, headers)
        assert first['status']=='complete', first
        assert first['reports']['1']['mesh']['triangles']>0
        assert client.get(first_path+'/views/1/original', headers=headers).content==scan

        preview_path = submit('smooth', base=first['id'], settings={'smoothing':8})
        preview = wait(client, preview_path, headers)
        assert preview['status']=='complete', preview
        assert preview['settings']['depth']==7 and preview['settings']['smoothing']==8
        assert client.get(preview_path+'/views/1/cleaned', headers=headers).content==client.get(first_path+'/views/1/cleaned', headers=headers).content
        latest = base+'/sources/'+source+'/latest'
        assert client.get(latest, headers=headers).json()['id']==first['id']
        assert client.post(preview_path+'/apply', headers=headers).status_code==200
        assert client.get(latest, headers=headers).json()['id']==preview['id']

        cancelled_path = submit('reconstruct', settings={'depth':7})
        assert client.delete(cancelled_path, headers=headers).status_code==200
        assert wait(client, cancelled_path, headers)['status']=='cancelled'
        assert client.get(cancelled_path+'/views/1/mesh', headers=headers).status_code==404
        assert client.get(latest, headers=headers).json()['id']==preview['id']
