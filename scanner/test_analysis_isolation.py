import concurrent.futures
import json
import unittest
from unittest.mock import patch

import analysis


class AnalysisIsolationTests(unittest.TestCase):
    def test_response_from_a_different_request_is_rejected(self):
        client = analysis.Worker()
        try:
            stale = json.dumps({'requestId': 'another-request',
                                'result': {'version': 1}}).encode() + b'\n'
            with patch.object(analysis.Worker, '_readline', return_value=stale):
                with self.assertRaisesRegex(analysis.AnalysisRuntimeError, 'request ID'):
                    client.request({'version': 1, 'operation': 'ping'})
            # the client whose response did not match is discarded wholesale, so
            # a later repository can never reuse the stale pipe
            self.assertIsNone(client.process)
        finally:
            client.close()

    def test_concurrent_requests_never_receive_another_repository_result(self):
        # production hands out one Worker per thread (thread-local), so pipes
        # never carry two in-flight requests
        clients = []
        original_spawn = analysis.Worker._spawn

        def tracking_spawn(self):
            clients.append(self)
            original_spawn(self)

        def request(number):
            client = analysis.worker()
            path = f'repository_{number}/index.js'
            result = client.request({'version': 1, 'files': {
                path: 'export function apply(ctx) { ctx.tools.register({name:"real"}); }'},
                'entries': [], 'candidates': [], 'nonRuntimePaths': []})
            self.assertEqual(len(result['registrations']), 1)
            self.assertEqual(result['registrations'][0]['path'], path)
            return number

        try:
            with patch.object(analysis.Worker, '_spawn', tracking_spawn):
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                    self.assertEqual(sorted(pool.map(request, range(12))), list(range(12)))
        finally:
            for client in clients:
                client.close()

    def test_sequential_requests_reuse_one_process(self):
        client = analysis.Worker()
        try:
            client.request({'version': 1, 'operation': 'ping'})
            first = client.process
            self.assertIsNotNone(first)
            client.request({'version': 1, 'operation': 'ping'})
            self.assertIs(client.process, first)
        finally:
            client.close()

    def test_worker_recycles_after_the_request_budget(self):
        client = analysis.Worker()
        spawns = []
        original_spawn = analysis.Worker._spawn

        def counting_spawn(self):
            spawns.append(self)
            original_spawn(self)

        try:
            with patch.object(analysis, 'RECYCLE_AFTER', 1), \
                    patch.object(analysis.Worker, '_spawn', counting_spawn):
                client.request({'version': 1, 'operation': 'ping'})
                self.assertIsNone(client.process)      # budget spent, process retired
                client.request({'version': 1, 'operation': 'ping'})
                self.assertIsNone(client.process)      # and again for the fresh one
            self.assertEqual(len(spawns), 2)           # one respawn per request, not per call forever
        finally:
            client.close()

    def test_a_killed_worker_fails_cleanly_and_respawns(self):
        client = analysis.Worker()
        try:
            client.request({'version': 1, 'operation': 'ping'})
            client.process.kill()
            client.process.wait()
            with self.assertRaisesRegex(analysis.AnalysisRuntimeError, 'Scanner analysis failed'):
                client.request({'version': 1, 'operation': 'ping'})
            self.assertIsNone(client.process)
            client.request({'version': 1, 'operation': 'ping'})    # respawn path works
            self.assertIsNotNone(client.process)
        finally:
            client.close()


if __name__ == '__main__':
    unittest.main()
