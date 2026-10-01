#!/usr/bin/env python3
"""Tests for salted sealing and private shares (ORDER_022), in a scratch PREDICT_HOME. The real repo is never touched.

  python3 scripts/predict/test_predict.py -v

The end-to-end tests run the real `ots` client: one `ots stamp` of a random test hash per run (public OpenTimestamps
calendars see only the hash). They are skipped when `ots` isn't installed. The negative controls check that a changed
file fails both the fingerprint check and `ots verify`, the two checks a recipient runs."""
import hashlib, json, os, re, shutil, subprocess, sys, tempfile, unittest, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ledger as L  # noqa: E402  (ROOT is unused below: the scripts run as subprocesses with PREDICT_HOME set)
import seal  # noqa: E402

SALT = re.compile(rb'\nsalt: [0-9a-f]{32}\n\Z')
HAVE_OTS = os.path.exists(L.OTS)


def sha(b): return hashlib.sha256(b).hexdigest()


def rd(p):
    with open(p, 'rb') as fh: return fh.read()


def wr(p, b):
    with open(p, 'wb') as fh: fh.write(b)


def tree(d):
    """{relative path: sha256} of every file under d, to show a directory was not written."""
    out = {}
    for root, _, files in os.walk(d):
        for f in files:
            p = os.path.join(root, f); out[os.path.relpath(p, d)] = sha(rd(p))
    return out


class SaltedCopy(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.d)

    def check(self, original):
        src, dst = os.path.join(self.d, 'p.md'), os.path.join(self.d, 'out.md')
        wr(src, original)
        salt = seal.salted_copy(src, dst)
        self.assertEqual(rd(src), original, 'the original must not change')
        self.assertRegex(salt, r'^[0-9a-f]{32}$')
        self.assertEqual(rd(dst), seal.with_newline(original) + f'salt: {salt}\n'.encode())
        return dst

    def test_with_final_newline(self):
        self.assertTrue(SALT.search(rd(self.check(b'Yes.\n'))))

    def test_without_final_newline(self):
        self.assertEqual(rd(self.check(b'Yes.'))[:5], b'Yes.\n')

    def test_salt_differs_each_time(self):
        a, b = rd(self.check(b'Yes.\n')), rd(self.check(b'Yes.\n'))
        self.assertNotEqual(sha(a), sha(b))

    def test_short_text_not_guessable_from_hash(self):
        # The attack the salt stops: hash every guess and compare with the public fingerprint.
        sealed = sha(rd(self.check(b'Yes.\n')))
        guesses = [g + nl for g in (b'Yes', b'Yes.', b'No', b'No.', b'yes', b'no') for nl in (b'', b'\n')]
        self.assertNotIn(sealed, {sha(g) for g in guesses})


@unittest.skipUnless(HAVE_OTS, 'ots client not installed')
class SealAndShare(unittest.TestCase):
    TEXT = b'Yes.\n'  # short and guessable on purpose

    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp()
        cls.env = {**os.environ, 'PREDICT_HOME': cls.home}
        cls.original = os.path.join(cls.home, 'mine.md')
        wr(cls.original, cls.TEXT)
        cls.mtime = os.stat(cls.original).st_mtime_ns
        cls.seal = cls.script('seal.py', cls.original, '--title', 'test')
        assert cls.seal.returncode == 0, cls.seal.stdout + cls.seal.stderr
        cls.ledger_path = os.path.join(cls.home, 'predictions', 'ledger.json')
        cls.entry = json.loads(rd(cls.ledger_path))['predictions'][0]
        cls.priv = os.path.join(cls.home, 'local', 'predictions', cls.entry['id'] + '.md')
        cls.public_before = tree(os.path.join(cls.home, 'predictions'))
        cls.share = cls.script('share.py', cls.entry['id'], '--to', 'Ana B.')
        cls.zip = os.path.join(cls.home, 'share', f'{cls.entry["id"]}_Ana-B.zip')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.home)

    @classmethod
    def script(cls, name, *args):
        return subprocess.run([sys.executable, os.path.join(HERE, name), *args], env=cls.env, capture_output=True, text=True)

    def unzip(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d)
        with zipfile.ZipFile(self.zip) as z: z.extractall(d)
        return d, os.path.join(d, self.entry['id'] + '.md'), os.path.join(d, self.entry['id'] + '.ots')

    def ots_verify(self, f, proof):
        return subprocess.run([L.OTS, '--no-bitcoin', 'verify', '-f', f, proof], capture_output=True, text=True)

    # seal.py
    def test_seal_hashes_the_salted_private_copy(self):
        data = rd(self.priv)
        self.assertTrue(data.startswith(self.TEXT) and SALT.search(data), data)
        self.assertEqual(self.entry['sha256'], sha(data))
        self.assertNotEqual(self.entry['sha256'], sha(self.TEXT), 'the public hash must not be the bare text hash')
        self.assertEqual((self.entry['status'], self.entry['salted']), ('sealed', True))

    def test_seal_leaves_the_original_untouched(self):
        self.assertEqual(rd(self.original), self.TEXT)
        self.assertEqual(os.stat(self.original).st_mtime_ns, self.mtime)

    def test_resealing_the_same_text_is_refused(self):
        before = rd(self.ledger_path)
        r = self.script('seal.py', self.original)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('already sealed as ' + self.entry['id'], r.stderr)
        self.assertEqual(rd(self.ledger_path), before)

    # share.py
    def test_share_packages_text_proof_readme(self):
        self.assertEqual(self.share.returncode, 0, self.share.stdout + self.share.stderr)
        names = sorted(zipfile.ZipFile(self.zip).namelist())
        self.assertEqual(names, sorted([self.entry['id'] + '.md', self.entry['id'] + '.ots', 'README.txt']))
        readme = zipfile.ZipFile(self.zip).read('README.txt').decode()
        for s in (self.entry['sha256'], 'shasum -a 256', 'ots --no-bitcoin verify', 'wknipe.com/predictions'):
            self.assertIn(s, readme)
        self.assertEqual(zipfile.ZipFile(self.zip).read(self.entry['id'] + '.md'), rd(self.priv))

    def test_share_publishes_nothing(self):
        self.assertEqual(tree(os.path.join(self.home, 'predictions')), self.public_before)
        self.assertEqual(json.loads(rd(self.ledger_path))['predictions'][0]['status'], 'sealed')

    def test_share_is_logged_locally(self):
        lines = rd(os.path.join(self.home, 'local', 'predictions', 'shares.log')).decode().splitlines()
        self.assertEqual(len([l for l in lines if l.split('\t')[2] == 'Ana B.']), 1)
        t, pid, name, z, digest = lines[0].split('\t')
        self.assertEqual((pid, z, digest), (self.entry['id'], os.path.join('share', os.path.basename(self.zip)), self.entry['sha256']))

    def test_share_refuses_a_tampered_private_file(self):
        good = rd(self.priv)
        try:
            wr(self.priv, good.replace(b'Yes', b'No!'))
            r = self.script('share.py', self.entry['id'], '--to', 'tamper')
        finally:
            wr(self.priv, good)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('hash mismatch', r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.home, 'share', f'{self.entry["id"]}_tamper.zip')))

    def test_share_unknown_id_fails(self):
        self.assertNotEqual(self.script('share.py', 'P-1999-01-01-01', '--to', 'x').returncode, 0)

    # what the recipient runs
    def test_recipient_positive_control(self):
        _, f, proof = self.unzip()
        self.assertEqual(sha(rd(f)), self.entry['sha256'])
        r = self.ots_verify(f, proof)
        out = r.stdout + r.stderr
        self.assertNotIn('File does not match original', out)
        # Day 0: the calendars haven't anchored the hash in Bitcoin yet, so "pending" (exit 1) is the expected result.
        self.assertTrue(r.returncode == 0 or 'Pending' in out, out)

    def test_recipient_negative_control_changed_text(self):
        _, f, proof = self.unzip()
        data = rd(f)
        wr(f, data.replace(b'Yes.', b'Yes!'))  # one byte
        self.assertNotEqual(sha(rd(f)), self.entry['sha256'])
        r = self.ots_verify(f, proof)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('File does not match original!', r.stdout + r.stderr)

    def test_recipient_negative_control_salt_removed(self):
        _, f, proof = self.unzip()
        wr(f, SALT.sub(b'\n', rd(f)))  # back to the bare text
        self.assertEqual(rd(f), self.TEXT)
        self.assertNotEqual(sha(rd(f)), self.entry['sha256'])
        r = self.ots_verify(f, proof)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('File does not match original!', r.stdout + r.stderr)


if __name__ == '__main__':
    unittest.main()
