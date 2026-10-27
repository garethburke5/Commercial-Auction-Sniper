"""Read-only Buffer connection and queue check. Never calls a mutation."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from marketing.buffer import Buffer


def inspect_queue(client, config, state):
    out = client.connection(config['organization_id'])
    remote = client.posts(config['organization_id'], list(config['channels'].values()))
    managed = {p.get('buffer_id'): key for key, p in state.get('posts', {}).items()}
    out['posts'] = [{key: post.get(key) for key in ('id', 'channelId', 'status', 'dueAt')}
                    | {'managed_key': managed.get(post['id'])} for post in remote]
    out['scheduled_post_actions'] = []
    for post in remote:
        if post['status'] == 'scheduled' and post['id'] in managed:
            details = client.request(
                'query($id:PostId!){ post(input:{id:$id}) { id status dueAt allowedActions } }',
                {'id': post['id']})
            out['scheduled_post_actions'].append(details)
    return out


if __name__ == '__main__':
    config = json.loads(Path('marketing/config.json').read_text())
    state = json.loads(Path('marketing/state.json').read_text())
    result = inspect_queue(Buffer(budget=35), config, state)
    Path('social-output').mkdir(exist_ok=True)
    Path('social-output/connection.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
