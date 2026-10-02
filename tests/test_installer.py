import unittest
from unittest.mock import patch

import installer


class InstallerTests(unittest.TestCase):
    def template(self, version="1.4.0"):
        return {"id": "template-test", "display-name": "oke-rm-networking",
                "lifecycle-state": "ACTIVE", "freeform-tags": {
                    "installer": installer.INSTALLER, "asset": "oke-rm",
                    "template_type": "networking", "release_version": version}}

    def test_existing_match_is_skipped(self):
        template = self.template()
        self.assertEqual(installer.existing_template([template], "oke-rm-networking", "networking", "1.4.0"), template)

    def test_oci_template_collection_is_unwrapped(self):
        template = self.template()
        items = installer.template_items({"data": {"items": [template]}})
        self.assertEqual(installer.existing_template(items, "oke-rm-networking", "networking", "1.4.0"), template)

    def test_empty_collection_is_supported(self):
        self.assertEqual(installer.template_items({"data": {"items": []}}), [])

    def test_legacy_list_is_supported(self):
        self.assertEqual(installer.template_items({"data": [self.template()]}), [self.template()])

    def test_malformed_collection_fails_closed(self):
        for response in ({"data": {}}, {"data": {"items": ["not-a-template"]}}, {"data": None}):
            with self.subTest(response=response), self.assertRaises(ValueError):
                installer.template_items(response)

    def test_different_version_is_not_overwritten(self):
        with self.assertRaises(ValueError):
            installer.existing_template([self.template()], "oke-rm-networking", "networking", "1.5.0")

    def test_unowned_template_is_not_overwritten(self):
        template = self.template()
        template["freeform-tags"] = {}
        with self.assertRaises(ValueError):
            installer.existing_template([template], "oke-rm-networking", "networking", "1.4.0")

    def test_ambiguous_names_are_rejected(self):
        with self.assertRaises(ValueError):
            installer.existing_template([self.template(), self.template()], "oke-rm-networking", "networking", "1.4.0")

    def test_missing_template_is_created_later(self):
        self.assertIsNone(installer.existing_template([], "oke-rm-networking", "networking", "1.4.0"))

    def test_latest_release_filters_other_assets_and_prereleases(self):
        releases = [{"tag_name": tag, "draft": draft, "prerelease": pre}
                    for tag, draft, pre in [("oci-devops-rm-3.0.0", False, False),
                                           ("oke-rm-1.6.0", True, False),
                                           ("oke-rm-1.5.0", False, True),
                                           ("oke-rm-1.4.0", False, False)]]
        with patch.object(installer, "request_json", return_value=releases):
            self.assertEqual(installer.latest_release()["tag_name"], "oke-rm-1.4.0")

    def test_asset_must_come_from_the_selected_release(self):
        release = {"tag_name": "oke-rm-1.4.0", "assets": [{"name": "infra.zip", "browser_download_url": "https://example.com/infra.zip"}]}
        with self.assertRaises(ValueError):
            installer.archive_url(release, "infra.zip")

    def test_cancel_does_not_create_anything(self):
        release = {"tag_name": "oke-rm-1.4.0", "draft": False, "prerelease": False,
                   "assets": [{"name": filename, "browser_download_url":
                               f"https://github.com/{installer.SOURCE}/releases/download/oke-rm-1.4.0/{filename}"}
                              for filename in ("infra.zip", "oke.zip")]}
        answers = ["eu-amsterdam-1", "ocid1.tenancy.oc1..test", "both", "1.4.0",
                   "oke-rm-networking", "oke-rm-cluster", "no"]
        with patch("sys.argv", ["installer.py"]), patch.object(installer, "defaults", return_value=("", "")), \
                patch.object(installer, "prompt", side_effect=answers), \
                patch.object(installer, "latest_release", return_value=release), \
                patch.object(installer.shutil, "which", return_value="oci"), \
                patch.object(installer, "oci", return_value={"data": {"items": []}}) as cli:
            installer.main()
            self.assertEqual(cli.call_count, 1)
            self.assertEqual(cli.call_args.args[:3], ("resource-manager", "template", "list"))


if __name__ == "__main__":
    unittest.main()
