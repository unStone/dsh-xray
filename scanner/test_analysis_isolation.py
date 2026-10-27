import concurrent.futures
import json
import subprocess
import unittest
from unittest.mock import patch

import analysis


class AnalysisIsolationTests(unittest.TestCase):
    def test_response_from_a_different_request_is_rejected(self):
        client = analysis.Worker()
        result = subprocess.CompletedProcess([], 0, json.dumps({
            'requestId': 'another-request', 'result': {'version': 1}}).encode(), b'')
        with patch.object(analysis.subprocess, 'run', return_value=result):
            with self.assertRaisesRegex(analysis.AnalysisRuntimeError, 'request ID'):
                client.request({'version': 1, 'operation': 'ping'})

    def test_concurrent_requests_never_receive_another_repository_result(self):
        client = analysis.Worker()

        def request(number):
            path = f'repository_{number}/index.js'
            result = client.request({'version': 1, 'files': {
                path: 'export function apply(ctx) { ctx.tools.register({name:"real"}); }'},
                'entries': [], 'candidates': [], 'nonRuntimePaths': []})
            self.assertEqual(len(result['registrations']), 1)
            self.assertEqual(result['registrations'][0]['path'], path)
            return number

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sorted(pool.map(request, range(12))), list(range(12)))


if __name__ == '__main__':
    unittest.main()
