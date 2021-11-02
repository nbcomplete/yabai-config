import dataclasses as dc
import json
import subprocess
import sys

from enum import Enum
from collections import defaultdict
from typing import Tuple, List, Dict, Union


record = dc.dataclass(frozen=True)
mutable_record = dc.dataclass()


@record
class SpaceDef:
    label: str


@record
class SpaceSetup:
    display_for: Dict[SpaceDef, int]

    @property
    def spaces(self):
        return list(self.display_for.keys())


@record
class WindowSetup:
    space_for: Dict[str, SpaceDef]

    @property
    def app_titles(self):
        return list(self.space_for.keys())


main =  SpaceDef('main')
comm =  SpaceDef('comm')
org =  SpaceDef('org')
dev1 =  SpaceDef('dev1')
dev2 =  SpaceDef('dev2')


space_setups = {
    1: SpaceSetup({
        main: 1,
        comm: 1,
        org: 1,
        dev1: 1,
        dev2: 1,
    }),
    2: SpaceSetup({
        main: 2,
        comm: 2,
        org: 2,
        dev1: 1,
        dev2: 1,
    }),
    3: SpaceSetup({
        main: 3,
        comm: 3,
        org: 3,
        dev1: 1,
        dev2: 2,
    })
}


window_setup = WindowSetup({
    'Finder': main,
    'Preferences': main,
    'Preview': main,
    'Activity Monitor': main,

    'Safari': main,
    'Spotify': main,

    'Microsoft OneNote': main,
    'Microsoft Excel': main,
    'Microsoft Word': main,

    'Calendar': org,
    'Mail': org,
    'Reminders': org,

    'Messages': comm,
    'Signal': comm,
    'Discord': comm,
    'Slack': comm,
    'WhatsApp': comm,
    'Rambox': comm,
    'Microsoft Teams': comm,

    'PyCharm': dev1,
    'JetBrains Rider': dev1,
    'iTerm2': dev1,
    'Firefox': dev2,
    'Vivaldi': dev2,
})


@record
class Display:
    idx: int
    spaces: Tuple['Space']


@record
class Space:
    idx: int
    label: str


class YabaiError(Exception):
    pass


def invoke_yabai(command, *args, silent=False, **options) -> Union[str, Tuple[str, bool]]:
    cmd = ['yabai', '-m', command]
    for arg in args:
        cmd.append(str(arg))
    for name, value in options.items():
        cmd.append(f'--{name}')
        cmd.append(str(value))

    print('yabai cmd', cmd)
    proc = subprocess.run(cmd, capture_output=True, text=True)

    if silent:
        return proc.stdout, (proc.returncode == 0)
    else:
        if proc.returncode != 0:
            raise YabaiError(f'yabai returned {proc.returncode}, stderr: {proc.stderr}, cmd: {cmd}')
        return proc.stdout


def config(key, value=None):
    if value is None:
        return invoke_yabai('config', key)
    
    if config(key) != value:
        return invoke_yabai('config', key, value)


def query(topic, **filters):
    return json.loads(invoke_yabai('query', f'--{topic}', **filters))


def move_window(window_id, *, display_idx=None, space_label=None):
    assert display_idx or space_label
    assert not (display_idx and space_label)

    option = {'display': display_idx} if display_idx else {'space': space_label}
    _, success = invoke_yabai('window', window_id, **option, silent=True)

    return success


def create_space(label=None, display_idx=None):
    invoke_yabai('space', '--create')
    if label or display_idx:
        new_space_idx = query('displays', display='')['spaces'][-1]
        if label:
            invoke_yabai('space', new_space_idx, label=label)
        if display_idx:
            try:
                invoke_yabai('space', new_space_idx, display=display_idx)
            except YabaiError as e:
                if 'space is already' not in str(e):
                    raise


def destroy_space(idx=None, label=None):
    assert idx or label
    assert not (idx and label)
    invoke_yabai('space', idx or label, '--destroy')


def move_space_on_display(label, target_idx):
    return invoke_yabai('space', label, move=target_idx)


def move_space(space=None, space_label=None, display_idx=None):
    assert display_idx
    assert space or space_label
    assert not (space and space_label)
    if space:
        assert space['label']
    else:
        try:
            space = query('spaces', space=space_label)
        except YabaiError as e:
            if 'could not locate the selected space' in str(e):
                return create_space(label=space_label, display_idx=display_idx)
            raise
    
    if space['display'] == display_idx:
        return True
    
    display = query('displays', display=space['display'])
    only_space = (len(display['spaces']) == 1)
    if only_space:
        create_space(display_idx=space['display'])
    
    invoke_yabai('space', space['label'], display=display_idx)


def do_setup():
    current_spaces = query('spaces')
    displays_in_use = 0
    space_locations = {}
    spaces_by_label = {}
    spaces_by_window_id = {}
    for space in current_spaces:
        if space['label']:
            spaces_by_label[space['label']] = space
            for window_id in space['windows']:
                spaces_by_window_id[window_id] = space
        display_idx = space['display']
        key = space['label'] or space['index']
        space_locations[key] = display_idx
        if display_idx > displays_in_use:
            displays_in_use = display_idx
        
    active_setup: SpaceSetup = space_setups.get(displays_in_use, 1)
    print('using setup', displays_in_use)
    needed_spaces: List[SpaceDef] = active_setup.spaces
    space_order_per_display = defaultdict(list)
    for space in needed_spaces:
        correct = active_setup.display_for[space]
        current = space_locations.get(space.label)
        if current is None:
            create_space(label=space.label, display_idx=correct)
        elif current != correct:
            print('moving space', space.label, correct)
            move_space(spaces_by_label[space.label], display_idx=correct)
        else:
            print('space', space.label, 'correct')
        space_order_per_display[correct].append(space)

    managed_labels = set(s.label for s in needed_spaces)
    spaces_to_destroy = []
    for space in query('spaces'):
        if not space['label'] or space['label'] not in managed_labels:
            print('deferring destroy space', space['index'], space['label'])
            spaces_to_destroy.append(space['index'])

    for idx in sorted(spaces_to_destroy, reverse=True):
        print('destroying space', idx)
        try:
            destroy_space(idx=idx)
        except YabaiError as e:
            print('destroy space failed', idx, e)

    print('correct space order per display', space_order_per_display)
    num_prev_spaces = 0
    for display_idx in sorted(space_order_per_display):
        spaces = space_order_per_display[display_idx]
        for correct_idx, space in enumerate(spaces, num_prev_spaces + 1):
            try:
                move_space_on_display(space.label, correct_idx)
            except YabaiError as e:
                if 'to itself' not in str(e):
                    print('reordering space failed', space.label, correct_idx, e)
        num_prev_spaces += len(spaces)


    # if displays_in_use == 1:
    config('layout', 'stack')
    # else:
    #    config('layout', 'bsp')
    #    for label in ['main', 'org', 'comm', 'dev2']:
    #        invoke_yabai('space', label, layout='stack')

    windows_by_app = defaultdict(list)
    for window in query('windows'):
        windows_by_app[window['app']].append(window)

    for app_title in window_setup.app_titles:
        windows = windows_by_app.pop(app_title, [])
        for window in windows:
            target_space = window_setup.space_for[app_title]
            current_space = spaces_by_window_id.get(window['id'])
            if current_space and target_space.label == current_space['label']:
                print('window', app_title, window['id'], 'correct')
            else:
                print('moving window', app_title, window['id'], target_space.label)
                move_window(window['id'], space_label=target_space.label)

    for windows in windows_by_app.values():
        for window in windows:
            move_window(window['id'], space_label=main.label)
    
    invoke_yabai('space', focus=main.label)


if '--safe' in sys.argv:
    for _ in range(2):
        do_setup()
else:
    do_setup()
