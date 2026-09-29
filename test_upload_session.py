import os
import tempfile
import unittest

from fastapi.testclient import TestClient

import api


class UploadSessionTests(unittest.TestCase):
    def setUp(self):
        api.reset()

    def test_new_upload_starts_fresh_session(self):
        client = TestClient(api.app)

        first = tempfile.NamedTemporaryFile('wb', suffix='.jsonl', delete=False)
        first.write(b'{"rideid":"R1","userid":"U1"}\n')
        first.close()

        second = tempfile.NamedTemporaryFile('wb', suffix='.csv', delete=False)
        second.write(b'src_addr,dst_addr,status\n10.0.0.1,10.0.0.2,ok\n')
        second.close()

        try:
            r1 = client.post('/api/upload', files={'file': ('one.jsonl', open(first.name, 'rb'), 'application/json')}, data={'format_type': 'json', 'source_type': 'db'})
            self.assertEqual(r1.status_code, 200)

            r2 = client.post('/api/upload', files={'file': ('two.csv', open(second.name, 'rb'), 'text/csv')}, data={'format_type': 'csv', 'source_type': 'network'})
            self.assertEqual(r2.status_code, 200)

            status = client.get('/api/status')
            self.assertEqual(status.json()['total_files'], 1)
            self.assertEqual(status.json()['total_records'], 1)
        finally:
            os.unlink(first.name)
            os.unlink(second.name)


if __name__ == '__main__':
    unittest.main()
