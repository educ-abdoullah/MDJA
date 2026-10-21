"""Tests unitaires de l'etape 4 (pytest ou unittest via discovery)."""
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from gazette.collectors import rss


class RetryTests(unittest.TestCase):
    def test_transient_and_permanent_errors(self):
        self.assertTrue(rss.is_transient_error(HTTPError('http://test', 503, 'unavailable', {}, None)))
        self.assertTrue(rss.is_transient_error(URLError('timeout')))
        self.assertFalse(rss.is_transient_error(HTTPError('http://test', 403, 'forbidden', {}, None)))
        self.assertFalse(rss.is_transient_error(ValueError('invalid RSS')))

    def test_failure_record_query(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (3, 'sleep time')
        result = rss.record_source_failure(conn, 'lemonde', ValueError('bad'))
        self.assertTrue(result['en_sommeil'])
        self.assertEqual(result['echecs_consecutifs'], 3)
        self.assertIn('echecs_consecutifs + 1', cursor.execute.call_args.args[0])
        conn.commit.assert_called_once()

    def test_success_resets_counter(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.rowcount = 1
        source = {'source_id': 'lemonde', 'url': 'https://example.org/rss'}
        with patch.object(rss, 'fetch_feed_conditional', return_value=(None,304,None,None)):
            result = rss.collect_source_to_storage(conn,source,MagicMock())
        self.assertEqual(result['http_status'],304)
        query = cursor.execute.call_args.args[0]
        self.assertIn('echecs_consecutifs = 0',query)
        self.assertIn('sommeil_depuis = NULL',query)
        conn.commit.assert_called_once()

    def test_retry_503_only_counts_one_cycle(self):
        source = {'source_id': 'lemonde', 'url': 'https://example.org/rss'}
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value.fetchall.return_value = []
        cm = MagicMock()
        cm.__enter__.return_value=conn
        cm.__exit__.return_value=False
        error = HTTPError('http://test',503,'unavailable',{},None)
        with patch('psycopg2.connect',return_value=conn), \
             patch.object(rss,'load_sources_from_db',return_value=[source]), \
             patch.object(rss,'collect_source_to_storage',side_effect=[error,error,error]) as collect, \
             patch.object(rss,'record_source_failure',return_value={'error':'503','echecs_consecutifs':1,'en_sommeil':False}) as record, \
             patch.object(rss.time,'sleep') as sleep:
            result=rss.collect_active_sources('url',MagicMock())
        self.assertEqual(collect.call_count,3)
        self.assertEqual(record.call_count,1)
        self.assertEqual([x.args[0] for x in sleep.call_args_list],[1,2])
        self.assertEqual(result['lemonde']['tentatives'],3)

    def test_403_does_not_retry(self):
        source={'source_id':'le-telegramme','url':'https://example.org/rss'}
        conn=MagicMock()
        error=HTTPError('https://example.org/rss',403,'forbidden',{},None)
        with patch('psycopg2.connect',return_value=conn), \
             patch.object(rss,'load_sources_from_db',return_value=[source]), \
             patch.object(rss,'collect_source_to_storage',side_effect=error) as collect, \
             patch.object(rss,'record_source_failure',return_value={'error':'403','echecs_consecutifs':1,'en_sommeil':False}) as record, \
             patch.object(rss.time,'sleep') as sleep:
            result=rss.collect_active_sources('url',MagicMock())
        self.assertEqual(collect.call_count,1)
        self.assertEqual(record.call_count,1)
        sleep.assert_not_called()
        self.assertEqual(result['le-telegramme']['tentatives'],1)

if __name__ == '__main__':
    unittest.main()
