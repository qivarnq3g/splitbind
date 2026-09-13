import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "release-images.yaml"


class ReleaseImagesWorkflowContractTest(unittest.TestCase):
    def test_release_images_workflow_preserves_the_integrity_release_contract(self):
        self.assertTrue(WORKFLOW.is_file(), "release image workflow must exist")
        workflow = WORKFLOW.read_text(encoding="utf-8")

        required_fragments = (
            "name: release-images",
            "integrity-v*",
            "pull_request:",
            "runs-on: ubuntu-24.04",
            "python-version-file: .python-version",
            "node-version-file: .nvmrc",
            "npm install --global npm@12.0.1 --ignore-scripts",
            "python infra/scripts/run_smoke.py --release",
            "needs: verify",
            "if: github.event_name != 'pull_request'",
            "contents: read",
            "packages: write",
            "username: ${{ github.actor }}",
            "password: ${{ secrets.GITHUB_TOKEN }}",
            "platforms: linux/amd64",
            "file: infra/docker/api.Dockerfile",
            "file: infra/docker/web.Dockerfile",
            "tags: ghcr.io/${{ github.repository_owner }}/splitbind-api",
            "tags: ghcr.io/${{ github.repository_owner }}/splitbind-web",
            "cache-from: type=gha",
            "cache-to: type=gha,mode=max",
            "sbom: true",
            "provenance: true",
            "steps.api.outputs.digest",
            "steps.web.outputs.digest",
            "API_IMAGE=ghcr.io/${{ github.repository_owner }}/splitbind-api@${API_DIGEST}",
            "WEB_IMAGE=ghcr.io/${{ github.repository_owner }}/splitbind-web@${WEB_DIGEST}",
            "retention-days: 1",
            "group: ${{ github.workflow }}-${{ github.ref }}",
            "cancel-in-progress: true",
        )
        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, workflow)

        trigger_block = workflow.split("concurrency:", 1)[0]
        self.assertIn("push:", trigger_block)
        self.assertIn("tags:", trigger_block)
        self.assertIn("- integrity-v*", trigger_block)
        self.assertNotIn("branches:", trigger_block)

        action_shas = {
            "actions/checkout": "11bd71901bbe5b1630ceea73d27597364c9af683",
            "actions/setup-python": "a26af69be951a213d495a4c3e4e4022e16d87065",
            "actions/setup-node": "49933ea5288caeca8642d1e84afbd3f7d6820020",
            "docker/setup-buildx-action": "e468171a9de216ec08956ac3ada2f0791b6bd435",
            "docker/login-action": "74a5d142397b4f367a81961eba4e8cd7edddf772",
            "docker/build-push-action": "263435318d21b8e681c14492fe198d362a7d2c83",
            "actions/upload-artifact": "ea165f8d65b6e75b540449e92b4886f43607fa02",
        }
        for action, sha in action_shas.items():
            with self.subTest(action=action):
                self.assertIn(f"uses: {action}@{sha}", workflow)

        self.assertNotRegex(workflow, r"uses:\s+[^@\s]+@(?![0-9a-f]{40}(?:\s|$))")
        self.assertNotIn("secrets.", workflow.replace("secrets.GITHUB_TOKEN", ""))


if __name__ == "__main__":
    unittest.main()
