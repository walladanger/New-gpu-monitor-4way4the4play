import unittest

from ambient_theme import BG, PANEL, HIGHLIGHT, PERIOD, gradient_image, shade
from window_chrome import edge_hit_test,resized_bounds


class AmbientTests(unittest.TestCase):
    def test_highlights_remain_close_to_original_palette(self):
        for base in (BG,PANEL):
            original = tuple(int(base[i:i+2],16) for i in (1,3,5))
            for phase in (0,.25,.5,.75):
                for position in (0,.2,.5,.9,1):
                    color = shade(base,position,phase)
                    self.assertTrue(all(0 <= value-old <= limit for value,old,limit in zip(color,original,HIGHLIGHT)))

    def test_gradient_is_horizontal_and_continuous_across_panels(self):
        full = gradient_image(1000,30,PANEL,1000,0,.15)
        piece = gradient_image(320,15,PANEL,1000,240,.15)
        for x in range(320):
            self.assertEqual(full.getpixel((240+x,0)),piece.getpixel((x,14)))
        self.assertNotEqual(full.getpixel((0,0)),full.getpixel((500,0)))

    def test_animation_changes_slowly_without_flashes(self):
        for position in (0,.25,.5,.75,1):
            a,b = shade(BG,position,.25),shade(BG,position,.25+.5/PERIOD)
            self.assertTrue(all(abs(left-right)<=1 for left,right in zip(a,b)))
        a = gradient_image(1000,1,BG,1000,0,.1)
        b = gradient_image(1000,1,BG,1000,0,.5)
        self.assertNotEqual(a.tobytes(),b.tobytes())


class HitTestTests(unittest.TestCase):
    def test_manual_resize_preserves_opposite_edge_and_minimum_size(self):
        self.assertEqual(resized_bounds((100,100,800,600),'nw',-40,-30,(450,400)),(60,70,840,630))
        self.assertEqual(resized_bounds((100,100,800,600),'w',1000,0,(450,400)),(450,100,450,600))
        self.assertEqual(resized_bounds((100,100,800,600),'se',-1000,-1000,(450,400)),(100,100,450,400))
    def test_every_resize_edge_and_corner_and_maximized_client(self):
        box = (100,100,900,700)
        for point,expected in (((101,101),13),((899,101),14),((101,699),16),((899,699),17),
                               ((500,101),12),((500,699),15),((101,400),10),((899,400),11),((500,400),1)):
            self.assertEqual(edge_hit_test(box,*point),expected)
            self.assertEqual(edge_hit_test(box,*point,maximized=True),1)
