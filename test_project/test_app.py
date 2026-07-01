import unittest
from app import calculate_total, find_max, UserStore

class TestCalculateTotal(unittest.TestCase):
    def test_normal(self):
        self.assertEqual(calculate_total([1, 2, 3, 4, 5]), 15)
    
    def test_empty(self):
        self.assertEqual(calculate_total([]), 0)
    
    def test_negative(self):
        self.assertEqual(calculate_total([-1, -2, -3]), -6)

class TestFindMax(unittest.TestCase):
    def test_normal(self):
        self.assertEqual(find_max([3, 1, 4, 1, 5, 9, 2, 6]), 9)
    
    def test_single(self):
        self.assertEqual(find_max([42]), 42)

class TestUserStore(unittest.TestCase):
    def test_add_and_find(self):
        store = UserStore()
        store.add("alice", 30)
        store.add("bob", 25)
        result = store.find("alice")
        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "alice")
        self.assertEqual(result["age"], 30)
    
    def test_find_not_found(self):
        store = UserStore()
        self.assertIsNone(store.find("nobody"))

if __name__ == "__main__":
    unittest.main()
