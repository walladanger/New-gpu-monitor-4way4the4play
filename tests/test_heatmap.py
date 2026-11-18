import unittest

from gpu_data import Reading, Snapshot
from heatmap import bucket_intervals, render_heatmap
from preferences import validate
from resource_analytics import occupancy_resolution


def gpu(index, power):
    return Reading(str(index), f'GPU-{index}', 'RTX 3090', 50, 16, 24, 60, power, 310)


def snapshot(stamp, *readings):
    return Snapshot(stamp, 1_700_000_000 + stamp, readings)


class HeatmapTests(unittest.TestCase):
    def test_system_heatmap_has_more_detail_on_large_panels(self):
        self.assertEqual(occupancy_resolution(1200, 500, 300), (100, 48))
        self.assertEqual(occupancy_resolution(320, 180, 60), (56, 20))

    def test_coverage_clips_intervals_and_does_not_fill_gaps_or_tail(self):
        records = [snapshot(0, gpu(0, 105)), snapshot(1.2, gpu(0, 0)),
                   snapshot(2, gpu(0, None)), snapshot(3, gpu(0, 99)),
                   snapshot(8, gpu(0, 210)), snapshot(9, gpu(0, 310))]
        cells, coverage = bucket_intervals(records, 'power', ['GPU-0'], .2, 10.2, 10, 32, 10)
        self.assertAlmostEqual(cells['GPU-0'][0, 10], 1)
        self.assertAlmostEqual(cells['GPU-0'][1, 0], .8)
        self.assertEqual(coverage['GPU-0'][2:7], [0] * 5)
        self.assertAlmostEqual(cells['GPU-0'][7, 21], .2)
        self.assertAlmostEqual(cells['GPU-0'][8, 21], .8)
        self.assertEqual(coverage['GPU-0'][9], 0)
        self.assertAlmostEqual(sum(coverage['GPU-0']), 2.8)

    def test_render_keeps_gpus_separate_and_hover_matches_the_painted_cell(self):
        a, b = gpu(0, 305), gpu(1, 65)
        devices = {item.uuid: item for item in (a, b)}
        colors = {'GPU-0': '#56d6be', 'GPU-1': '#70a9ff'}
        records = [snapshot(stamp, a, b) for stamp in range(121)]
        scene = render_heatmap('power', 900, 500, records, devices, colors, None, 120, 120)
        self.assertEqual(scene.columns, 120)
        self.assertGreaterEqual(scene.rows_count, 30)
        first, second = scene.lanes
        self.assertTrue(all(row == 305 // scene.value_step for _, row in first.cells))
        self.assertTrue(all(row == 65 // scene.value_step for _, row in second.cells))
        row = scene.rows_count - 1 - int(305 // scene.value_step)
        bounds, label = scene.cell_at(scene.x_edges[17], first.y_edges[row])
        self.assertEqual(bounds[:2], (scene.x_edges[17], first.y_edges[row]))
        self.assertIn('RTX 3090 #1', label)
        self.assertIn('1.00s estimated in band', label)
        self.assertIsNone(scene.cell_at(0, 0))

    def test_preferences_preserve_modes_and_default_to_line(self):
        state = validate({'schema': 1, 'main': {'charts': {
            'power': {'graph_mode': 'heatmap'}, 'memory': {}, 'temperature': {'graph_mode': 'unknown'}},
            'replay_modes': {'power': 'heatmap', 'unknown': 'heatmap'}},
            'detached': [{'metric': 'power', 'graph_mode': 'heatmap'}]})
        self.assertEqual(state['main']['charts']['power']['graph_mode'], 'heatmap')
        self.assertEqual(state['main']['charts']['memory']['graph_mode'], 'line')
        self.assertEqual(state['main']['charts']['temperature']['graph_mode'], 'line')
        self.assertEqual(state['main']['replay_modes'], {'power': 'heatmap'})
        self.assertEqual(state['detached'][0]['graph_mode'], 'heatmap')
