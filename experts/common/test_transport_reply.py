import unittest

from accept import transport_error_reply


class TransportReplyTests(unittest.TestCase):
    def test_actual_acp_provider_failure_is_not_an_ordinary_answer(self):
        reply = 'turn_failed APIError: litellm.APIError: OpenrouterException - Upstream HTTP 403: Key limit exceeded (code -32099)'
        self.assertTrue(transport_error_reply(reply).startswith('ProviderTransportError:'))

    def test_normal_work_discussing_errors_is_not_flagged(self):
        self.assertIsNone(transport_error_reply('接口返回 HTTP 403，需要核对权限。'))
        self.assertIsNone(transport_error_reply('报告里记录了 turn_failed APIError: 示例。'))


if __name__ == '__main__':
    unittest.main()
