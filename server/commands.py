# TsuserverDR, a Danganronpa Online server based on tsuserver3, an Attorney Online server
#
# Copyright (C) 2016 argoneus <argoneuscze@gmail.com> (original tsuserver3)
# Current project leader: 2018-19 Chrezm/Iuvee <thechrezm@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# possible keys: ip, OOC, id, cname, ipid, hdid

import random
import hashlib
import string
import time
import traceback

from server import logger
from server.constants import Constants, TargetType
from server.exceptions import ClientError, ServerError, ArgumentError, AreaError, PartyError

""" <parameter_name>: required parameter
{parameter_name}: optional parameter
"""

def ooc_cmd_announce(client, arg):
    """ (MOD ONLY)
    Sends an "announcement" to all users in the server, regardless of whether they have global chat
    turned on or off.
    Returns an error if user sends an empty message.

    SYNTAX
    /announce <message>

    PARAMETERS
    <message>: Message to be sent

    EXAMPLE
    /announce Hello World       :: Sends Hello World to all users in the server.
    """

    try:
        Constants.command_assert(client, arg, is_mod=True, parameters='>0')
    except ArgumentError:
        raise ArgumentError('You cannot send an empty announcement.')

    client.server.send_all_cmd_pred('CT', '{}'.format(client.server.config['hostname']),
                                    '=== Announcement ===\r\n{}\r\n=================='.format(arg))
    logger.log_server('[{}][{}][ANNOUNCEMENT]{}.'
                      .format(client.area.id, client.get_char_name(), arg), client)

def ooc_cmd_area(client, arg):
    """
    Either lists all areas in the server or switches the user to a new given area.
    Returns an error if user is unathorized to list all areas or unable to move to the intended new
    area.

    SYNTAX
    /area {new_area_id}

    OPTIONAL PARAMETERS
    {new_area_id}: ID of the area

    EXAMPLES
    /area       :: Lists all areas in the server along with their user count.
    /area 1     :: Moves you to area 1
    """

    args = arg.split()
    # List all areas
    if len(args) == 0:
        if client.in_rp:
            client.send_limited_area_list()
        else:
            client.send_area_list()

    # Switch to new area
    elif len(args) == 1:
        try:
            area = client.server.area_manager.get_area_by_id(int(args[0]))
            client.change_area(area, from_party=(client.party is not None))
        except ValueError:
            raise ArgumentError('Area ID must be a number.')
    else:
        raise ArgumentError('Too many arguments. Use /area <id>.')

def ooc_cmd_area_kick(client, arg):
    """ (STAFF ONLY)
    Kicks a player by client ID or IPID to a given area by ID or name, or the default area if not
    given an area. GMs cannot perform this command on users in lobby areas.
    If given IPID, it will kick all clients opened by the user. Otherwise, it will just kick the
    given client.
    Returns an error if the given identifier does not correspond to a user, or if there was some
    sort of error in the process of kicking the user to the area (e.g. full area).

    SYNTAX
    /area_kick <client_id> {target_area}
    /area_kick <client_ipid> {target_area}

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)
    <client_ipid>: IPID for the client (number in parentheses in /getarea)

    OPTIONAL PARAMETERS
    {target_area}: Intended area to kick the player, by ID or name

    EXAMPLES
    Assuming the default area of the server is area 0...
    /area_kick 1                        :: Kicks the player whose client ID is 1 to area 0.
    /area_kick 1234567890 3             :: Kicks all the clients opened by the player whose IPID is 1234567890 to area 3.
    /area_kick 0987654321 Lobby         :: Kicks all the clients opened by the player whose IPID is 0987654321 to Lobby.
    /area_kick 3 Class Trial Room,\ 2   :: Kicks the player whose client ID is 1 to Class Trial Room, 2 (note the ,\).
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')
    if not client.is_mod and not client.is_cm and client.area.lobby_area:
        raise ClientError('You must be authorized to kick clients in lobby areas.')

    arg = arg.split(' ')
    if len(arg) == 1:
        area = client.server.area_manager.get_area_by_id(client.server.default_area)
    else:
        area = Constants.parse_area_names(client, [" ".join(arg[1:])])[0]

    for c in Constants.parse_id_or_ipid(client, arg[0]):
        # Failsafe in case kicked player has their character changed due to its character being used
        current_char = c.displayname
        try:
            c.change_area(area, override_passages=True, override_effects=True, ignore_bleeding=True)
        except ClientError as error:
            error_mes = ", ".join([str(s) for s in error.args])
            client.send_ooc('Unable to kick {} to area {}: {}'
                            .format(current_char, area.id, error_mes))
        else:
            client.send_ooc('Kicked {} to area {}.'.format(current_char, area.id))
            c.send_ooc("You were kicked from the area to area {}.".format(area.id))
            if client.area.is_locked or client.area.is_modlocked:
                try: # Try and remove the IPID from the area's invite list
                    client.area.invite_list.pop(c.ipid)
                except KeyError:
                    pass # Would only happen if client joins through mod powers to the locked area

            if client.party:
                party = client.party
                party.remove_member(client)
                client.send_ooc('You were also kicked off your party.')
                for member in party.get_members():
                    member.send_ooc('{} was area kicked off your party.'.format(current_char))

def ooc_cmd_area_list(client, arg):
    """ (MOD ONLY)
    Sets the server's current area list (what areas exist at any given time). If given no arguments,
    it will return the area list to its original value (in areas.yaml). The list of area lists can
    be accessed with /area_lists. Clients that do not process 'SM' packets can be in servers that
    use this command without crashing, but they will continue to only see the areas they could see
    when joining.
    Returns an error if the given area list was not found.

    SYNTAX
    /area_list <area_list>

    PARAMETERS
    <area_list>: Name of the intended area list

    EXAMPLES
    /area_list dr1dr2       :: Load the "dr1dr2" area list.
    /area_list              :: Reset the area list to its original value.
    """

    if not client.is_mod:
        raise ClientError('You must be authorized to do that.')

    if not arg:
        client.server.area_manager.load_areas()
        client.send_ooc('You have restored the original area list of the server.')
        client.send_ooc_others('The original area list of the server has been restored.',
                               is_staff=False)
        client.send_ooc_others('{} has restored the original area list of the server.'
                               .format(client.name), is_staff=True)
    else:
        try:
            new_area_file = 'config/area_lists/{}.yaml'.format(arg)
            client.server.area_manager.load_areas(area_list_file=new_area_file)
        except ServerError as exc:
            if exc.code == 'FileNotFound':
                raise ArgumentError('Could not find the area list file `{}`.'.format(new_area_file))
            raise # Weird exception, reraise it
        except AreaError as exc:
            raise ArgumentError('The area list {} returned the following error when loading: `{}`.'
                                .format(new_area_file, exc))

        client.send_ooc('You have loaded the area list {}.'.format(arg))
        client.send_ooc_others('The area list {} has been loaded.'.format(arg), is_staff=False)
        client.send_ooc_others('{} has loaded the area list {}.'.format(client.name, arg),
                               is_staff=True)

def ooc_cmd_area_lists(client, arg):
    """ (MOD ONLY)
    Lists all available area lists as established in config/area_lists.yaml. Note that, as this
    file is updated independently from the other area lists, an area list does not need to be in
    this file in order to be usable, and an area list in this list may no longer exist.

    SYNTAX
    /area_lists

    PARAMETERS
    None

    EXAMPLES
    /area_lists             :: Return all available area lists
    """

    if not client.is_mod:
        raise ClientError('You must be authorized to do that.')
    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    try:
        with Constants.fopen('config/area_lists.yaml', 'r') as f:
            output = 'Available area lists:\n'
            for line in f:
                output += '*{}'.format(line)
            client.send_ooc(output)
    except ServerError as exc:
        if exc.code == 'FileNotFound':
            raise ClientError('Server file area_lists.yaml not found.')

def ooc_cmd_autopass(client, arg):
    """
    Toggles enter/leave messages being sent automatically or not to users in the current area.
    It will not send those messages if the client is spectator or while sneaking. Altered messages
    will be sent if the area's lights are turned off.

    SYNTAX
    /autopass

    PARAMETERS
    None

    EXAMPLE
    /autopass
    """

    if len(arg) != 0:
        raise ArgumentError("This command has no arguments.")

    client.autopass = not client.autopass
    status = {False: 'off', True: 'on'}

    client.send_ooc('Autopass turned {}.'.format(status[client.autopass]))

def ooc_cmd_ban(client, arg):
    """ (MOD ONLY)
    Kicks given user from the server and prevents them from rejoining. The user can be identified
    by either their IPID or IP address. Requires /unban to undo.
    Returns an error if given identifier does not correspond to a user.

    SYNTAX
    /ban <client_ipid>
    /ban <client_ip>

    PARAMETERS
    <client_ipid>: IPID for the client (number in parentheses in /getarea)
    <client_ip>: user IP

    EXAMPLES
    /ban 1234567890             :: Bans the user whose IPID is 1234567890
    /ban 127.0.0.1              :: Bans the user whose IP is 127.0.0.1
    """

    arg = arg.strip()
    Constants.command_assert(client, arg, parameters='>0', is_mod=True)

    # Guesses that any number is an IPID
    # and that any non-numerical entry is an IP address.
    if arg.isdigit():
        # IPID
        idnt = int(arg)
        targets = client.server.client_manager.get_targets(client, TargetType.IPID, idnt, False)
    else:
        # IP Address
        idnt = arg
        targets = client.server.client_manager.get_targets(client, TargetType.IP, idnt, False)

    # Try and add the user to the ban list based on the given identifier
    client.server.ban_manager.add_ban(idnt)

    # Kick+ban all clients opened by the targeted user.
    if targets:
        for c in targets:
            client.send_ooc('You banned {} [{}/{}].'.format(c.displayname, c.ipid, c.hdid))
            client.send_ooc_others('{} was banned.'.format(c.displayname),
                                   pred=lambda x: not (x.is_mod or x.is_cm), in_area=True)
            client.send_ooc_others('{} banned {} [{}/{}].'
                                   .format(client.name, c.displayname, c.ipid, c.hdid),
                                   pred=lambda x: x.is_mod or x.is_cm)
            c.disconnect()

    client.send_ooc('You banned {}. As a result, {} clients were kickbanned.'
                    .format(idnt, len(targets)))
    client.send_ooc_others('{} banned {}. As a result, {} clients were kickbanned.'
                           .format(client.name, idnt, len(targets)),
                           pred=lambda c: c.is_mod or c.is_cm)
    logger.log_server('Banned {}.'.format(idnt), client)

def ooc_cmd_banhdid(client, arg):
    """ (MOD ONLY)
    Similar to /ban (kicks given user from the server if they are there and prevents them from
    rejoining), but the identifier must be an HDID. It does not require the player to be online.
    Requires /unbanhdid to undo.
    Returns an error if given identifier does not correspond to a user, or if the user is already
    banned.

    SYNTAX
    /banhdid <client_hdid>

    PARAMETERS
    <client_hdid>: User HDID (available in server logs and through a mod /whois)

    EXAMPLES
    /banhdid abcd1234             :: Bans the user whose HDID is abcd1234
    """

    Constants.command_assert(client, arg, parameters='=1', is_mod=True)

    if not arg in client.server.hdid_list:
        raise ClientError('Unrecognized HDID {}.'.format(arg))

    # This works by banning one of the IPIDs the player is associated with. The way ban handling
    # works is that the server keeps track of all the IPIDs a player has logged in with their HDID
    # and checks on joining if any of those IPIDs was banned in the past. If that is the case,
    # then the server assumes that player is banned, even if they have changed IPIDs in the meantime

    # Thus, banning one IPID is sufficient, so check if any associated IPID is already banned.
    for ipid in client.server.hdid_list[arg]:
        if client.server.ban_manager.is_banned(ipid):
            raise ClientError('Player is already banned.')

    identifier = random.choice(client.server.hdid_list[arg])
    # Try and add the user to the ban list based on the given identifier
    client.server.ban_manager.add_ban(identifier)

    # Try and kick the user from the server, as well as announce their ban.
    targets = client.server.client_manager.get_targets(client, TargetType.HDID, arg, False)

    # Kick+ban all clients opened by the targeted user.
    if targets:
        for c in targets:
            client.send_ooc('You HDID banned {} [{}/{}].'.format(c.displayname, c.ipid, c.hdid))
            client.send_ooc_others('{} was banned.'.format(c.displayname),
                                   pred=lambda x: not (x.is_mod or x.is_cm), in_area=True)
            client.send_ooc_others('{} HDID banned {} [{}/{}].'
                                   .format(client.name, c.displayname, c.ipid, c.hdid),
                                   pred=lambda x: x.is_mod or x.is_cm)
            c.disconnect()

    client.send_ooc('You banned HDID {}. As a result, {} clients were kickbanned.'
                    .format(arg, len(targets)))
    client.send_ooc_others('{} banned {}. As a result, {} clients were kickbanned.'
                           .format(client.name, arg, len(targets)),
                           pred=lambda c: c.is_mod or c.is_cm)
    logger.log_server('HDID-banned {}.'.format(identifier), client)

def ooc_cmd_bg(client, arg):
    """
    Change the background of the current area.
    Returns an error if area background is locked and the user is unathorized or if the sought
    background does not exist.

    SYNTAX
    /bg <background_name>

    PARAMETERS
    <background_name>: New background name, possibly with spaces (e.g. Principal's Room)

    EXAMPLES
    /bg Principal's Room   :: Changes background to Principal's Room
    """

    if len(arg) == 0:
        raise ArgumentError('You must specify a name. Use /bg <background>.')
    if not client.is_mod and client.area.bg_lock:
        raise AreaError("This area's background is locked.")

    client.area.change_background(arg, validate=not (client.is_staff() or client.area.cbg_allowed))
    client.area.broadcast_ooc('{} changed the background to {}.'
                              .format(client.displayname, arg))
    logger.log_server('[{}][{}]Changed background to {}'
                      .format(client.area.id, client.get_char_name(), arg), client)

def ooc_cmd_bglock(client, arg):
    """ (MOD ONLY)
    Toggles background changes by non-mods in the current area being allowed/disallowed.

    SYNTAX
    /bglock

    PARAMETERS
    None

    EXAMPLES
    /bglock
    """

    if not client.is_mod:
        raise ClientError('You must be authorized to do that.')
    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    client.area.bg_lock = not client.area.bg_lock
    client.area.broadcast_ooc('A mod has set the background lock to {}.'
                              .format(client.area.bg_lock))
    logger.log_server('[{}][{}]Changed bglock to {}'
                      .format(client.area.id, client.get_char_name(), client.area.bg_lock), client)

def ooc_cmd_bilock(client, arg):
    """ (VARYING REQUIREMENTS)
    Changes the passage status between given areas by name or ID. Passages are unidirectional, so
    to change a passage in just one direction, use /unilock instead.
    If given one area, it will change the passage status between the current area and the given one.
    If given two areas instead, it  will change the passage status between them (but requires
    staff role to use).
    Returns an error if the user is unauthorized to create new passages or change existing ones in
    any of the relevant areas. In particular, non-staff members are not allowed to create passages
    that did not exist when the areas were loaded or that a staff member did not create before.

    SYNTAX
    /bilock <target_area>
    /bilock <target_area_1>, <target_area_2>

    PARAMETERS
    <target_area>: Area whose passage status with the current area will be changed.
    <target_area_1>: Area whose passage status with <target_area_2> will be changed.
    <target_area_2>: Area whose passage status with <target_area_1> will be changed.

    EXAMPLES
    Assuming the player is in area 0 when executing these commands and originally the only existing
    passage lock is from area 1 'Class Trial Room' to area 2 'Class Trial Room, 2'...
    /bilock Class Trial Room            :: Locks the passage between area 0 and Class Trial Room.
    /bilock 1, 2                        :: Unlocks the passage from Class Trial Room to Class Trial
                                           Room, 2; and locks it from Class Trial Room, 2 to Class
                                           Trial Room.
    /bilock Class Trial Room,\ 2, 0     :: Locks the passage in both directions between areas 0
                                           and Class Trial Room, 2 (note the ,\ in the command.
    """

    areas = arg.split(', ')
    if len(areas) > 2 or arg == '':
        raise ArgumentError('This command takes one or two arguments.')
    if len(areas) == 2 and not client.is_staff():
        raise ClientError('You must be authorized to use the two-parameter version of this command.')

    areas = Constants.parse_two_area_names(client, areas, area_duplicate=False,
                                           check_valid_range=False)
    now_reachable = Constants.parse_passage_lock(client, areas, bilock=True)

    status = {True: 'unlocked', False: 'locked'}
    cname = client.name if client.is_staff() else client.displayname
    now0, now1 = status[now_reachable[0]], status[now_reachable[1]]
    name0, name1 = areas[0].name, areas[1].name

    if now_reachable[0] == now_reachable[1]:
        client.send_ooc('You have {} the passage between {} and {}.'.format(now0, name0, name1))
        client.send_ooc_others('(X) {} has {} the passage between {} and {} ({}).'
                               .format(cname, now0, name0, name1, client.area.id), is_staff=True)
        logger.log_server('[{}][{}]Has {} the passage between {} and {}.'
                          .format(client.area.id, client.get_char_name(), now0, name0, name1))

    else:
        client.send_ooc('You have {} the passage from {} to {} and {} it the other way around.'
                        .format(now0, name0, name1, now1))
        client.send_ooc_others('(X) {} has {} the passage from {} and {} and {} it the other way '
                               'around ({}).'.format(cname, now0, name0, name1, now1,
                                                     client.area.id), is_staff=True)
        logger.log_server('[{}][{}]Has {} the passage from {} to {} and {} it the other way around.'
                          .format(client.area.id, client.get_char_name(), now0, name0, name1, now1))

def ooc_cmd_blind(client, arg):
    """ (STAFF ONLY)
    Changes the blind status of a player by client ID.
    Blind players will receive no character sprites nor background with IC messages and cannot
    use "visual" commands such as /look, /getarea, etc.
    Immediately after blinding/unblinding, the target will receive sense-appropiate blood
    notifications in the area if needed (e.g. players bleeding, blood trails, etc.).
    Returns an error if the given identifier does not correspond to a user.

    SYNTAX
    /blind <client_id>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)

    EXAMPLES
    Assuming client 1 starts sighted...
    /blind 1            :: Blinds client 1
    /blind 1            :: Unblinds client 1
    """

    Constants.command_assert(client, arg, is_staff=True)
    target = Constants.parse_id(client, arg)

    status = {False: 'unblinded', True: 'blinded'}
    target.is_blind = not target.is_blind

    client.send_ooc('You have {} {}.'.format(status[target.is_blind], target.displayname))
    target.send_ooc('You have been {}.'.format(status[target.is_blind]))
    target.send_ooc_others('(X) {} has {} {} ({}).'
                           .format(client.name, status[target.is_blind], target.displayname,
                                   target.area.id), is_staff=True, not_to={client})

    if target.is_blind:
        target.send_command('BN', client.server.config['blackout_background'])
    else:
        target.send_command('BN', client.area.background)

    target.area_changer.notify_me_blood(target.area, changed_visibility=True, changed_hearing=False)

def ooc_cmd_blockdj(client, arg):
    """ (CM AND MOD ONLY)
    Revokes the ability of a player by client ID (number in brackets) or IPID (number in
    parentheses) to change music.
    If given IPID, it will affect all clients opened by the user. Otherwise, it will just affect
    the given client.
    Returns an error if the given identifier does not correspond to a user.

    SYNTAX
    /blockdj <client_id>
    /blockdj <client_ipid>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)
    <client_ipid>: IPID for the client (number in parentheses in /getarea)

    EXAMPLES
    /blockdj 1                     :: Revokes DJ permissions to the client whose ID is 1.
    /blockdj 1234567890            :: Revokes DJ permissions to all clients opened by the user whose IPID is 1234567890.
    """

    if not client.is_mod and not client.is_cm:
        raise ClientError('You must be authorized to do that.')

    # Block DJ permissions to matching targets
    for c in Constants.parse_id_or_ipid(client, arg):
        c.is_dj = False
        logger.log_server('Revoked DJ permissions to {}.'.format(c.ipid), client)
        client.area.broadcast_ooc("{} was revoked DJ permissions.".format(c.displayname))

def ooc_cmd_bloodtrail(client, arg):
    """ (STAFF ONLY)
    Toggles a client by IPID leaving a blood trail wherever they go or not. OOC announcements are
    made to players joining an area regarding the existence of a blood trail and where it leads to.
    Turning off a player leaving a blood trail does not clean the blood in the area. For that,
    use /bloodtrail_clean.
    Returns an error if the given identifier does not correspond to a user.

    SYNTAX
    /bloodtrail <client_id>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)

    EXAMPLE
    Assuming a player with client ID 0 and IPID 1234567890 starts as not being leaving a blood trail
    /bloodtrail 0            :: This player will now leave a blood trail wherever they go.
    """

    Constants.command_assert(client, arg, is_staff=True)
    target = Constants.parse_id(client, arg)

    status = {False: 'no longer', True: 'now'}
    status2 = {False: 'stop', True: 'start'}
    target.is_bleeding = not target.is_bleeding

    if target.is_bleeding:
        target.area.bleeds_to.add(target.area.name)

    target.send_ooc('You are {} bleeding.'.format(status[target.is_bleeding]))
    if target.is_visible and target.area.lights and target.area == client.area:
        connector = ''
    else:
        connector = '(X) '

    if target != client:
        client.send_ooc('{}You made {} {} bleeding.'
                        .format(connector, target.displayname, status2[target.is_bleeding]))
        target.send_ooc_others('(X) {} made {} {} bleeding ({}).'
                               .format(client.name, target.displayname,
                                       status2[target.is_bleeding], target.area.id),
                               is_staff=True, not_to={client})
    else:
        target.send_ooc_others('(X) {} made themselves {} bleeding ({}).'
                               .format(client.name, status2[target.is_bleeding], target.area.id),
                               is_staff=True, not_to={client})

    target.area_changer.notify_others_blood(target, target.area, target.displayname,
                                            status='stay', send_to_staff=False)

def ooc_cmd_bloodtrail_clean(client, arg):
    """
    Cleans the blood trails of the current area or (STAFF ONLY) given areas by ID or name separated
    by commas. If not given any areas, it will clean the blood trail of the current area.
    Blind non-staff players (or players in a dark area) who attempt to run this command will only
    smear the blood in the area, and regardless of whether there was blood or not, they will
    believe they cleaned it.
    Attempting to clean blood in a clean area or an area where there is someone bleeding will fail.

    SYNTAX
    /bloodtrail_clean {area_1}, {area_2}, ....

    OPTIONAL PARAMETERS
    {area_n}: Area ID or name

    EXAMPLE
    Assuming the player is in area 0
    /bloodtrail_clean                           :: Cleans the blood trail in area 0
    /bloodtrail_clean 3, Class Trial Room,\ 2   :: Cleans the blood trail in area 3 and Class Trial Room, 2 (note the ,\)
    """

    if not arg:
        areas_to_clean = [client.area]
    else:
        if not client.is_staff():
            raise ClientError('You must be authorized to do that.')
        # Make sure the input is valid before starting
        raw_areas_to_clean = arg.split(", ")
        areas_to_clean = set(Constants.parse_area_names(client, raw_areas_to_clean))

    successful_cleans = set()
    for area in areas_to_clean:
        if not area.bleeds_to and not area.blood_smeared:
            if client.is_staff() or not (client.is_blind or not area.lights):
                if not arg:
                    mes = 'You could not find any blood in the area.'
                else:
                    mes = 'There is no blood in area {}.'.format(area.name)
                client.send_ooc(mes)
                continue
            # Blind non-staff members will believe they clean the area.

        # Check if someone is currently bleeding in the area,
        # which would prevent it from being cleaned.
        # Yes, you can use for/else in Python, it works exactly like regular flags.
        for c in area.clients:
            if c.is_bleeding:
                mes = ''
                if not client.is_staff() and not client.is_blind:
                    mes = 'You tried to clean the place up, but the blood just keeps coming.'
                elif client.is_staff():
                    mes = ('(X) {} in area {} is still bleeding, so the area cannot be cleaned.'
                           .format(c.displayname, area.name))

                if mes:
                    client.send_ooc(mes)
                    break
        else:
            if (client.is_blind or not area.lights) and not (area.bleeds_to or area.blood_smeared):
                # Poke fun
                connector = '(X) ' if not client.area.lights else ''
                client.send_ooc_others('{}{} tried to clean the blood trail in the area, unaware '
                                       'that there was no blood to begin with.'
                                       .format(connector, client.displayname), in_area=area,
                                       is_staff=True)
                client.send_ooc_others('{} tried to clean the blood trail in the area, unaware '
                                       'that there was no blood to begin with.'
                                       .format(client.displayname), in_area=area,
                                       is_staff=False, to_blind=False, pred=lambda c: area.lights)
            elif not client.is_staff() and (client.is_blind or not area.lights):
                client.send_ooc_others('{} tried to clean the blood trail in the area, but only '
                                       'managed to smear it all over the place.'
                                       .format(client.displayname), is_staff=False,
                                       in_area=area, to_blind=False, pred=lambda c: area.lights)
                area.blood_smeared = True
            else:
                client.send_ooc_others('{} cleaned the blood trail in your area.'
                                       .format(client.displayname), is_staff=False,
                                       in_area=area, to_blind=False, pred=lambda c: area.lights)
                area.bleeds_to = set()
                area.blood_smeared = False
            successful_cleans.add(area.name)

    if successful_cleans:
        if not arg:
            message = client.area.name
            client.send_ooc('You cleaned the blood trail in your area.')
            connector = '(X) ' if not area.lights else ''
            aname1 = 'your area'
            aname2 = 'area {}'.format(client.area.name)

            if client.is_staff():
                mes = '{}{} cleaned the blood trail in {}.'
                client.send_ooc_others(mes.format(connector, client.name, aname1),
                                       is_staff=True, in_area=True)
                client.send_ooc_others(mes.format('(X) ', client.name, aname2),
                                       is_staff=True, in_area=False)
            else:
                mes = ''

                if (client.is_blind or not area.lights) and area.blood_smeared:
                    mes = ('{}{} tried to clean the blood trail in {}, but as they could not '
                           'see, they only managed to smear it all over the place.')
                elif not (client.is_blind or not area.lights):
                    mes = '{}{} cleaned the blood trail in {}.'

                client.send_ooc_others(mes.format(connector, client.displayname, aname1),
                                       is_staff=True, in_area=True)
                client.send_ooc_others(mes.format('(X) ', client.displayname, aname2),
                                       is_staff=True, in_area=False)

        elif len(successful_cleans) == 1:
            message = str(successful_cleans.pop())
            client.send_ooc('You cleaned the blood trail in area {}.'.format(message))
            client.send_ooc_others('(X) {} cleaned the blood trail in area {}.'
                                   .format(client.name, message), is_staff=True)
        elif len(successful_cleans) > 1:
            message = Constants.cjoin(successful_cleans)
            client.send_ooc('You cleaned the blood trails in areas {}.'.format(message))
            client.send_ooc_others('(X) {} cleaned the blood trails in areas {}.'
                                   .format(client.name, message), is_staff=True)
        logger.log_server('[{}][{}]Cleaned the blood trail in {}.'
                          .format(client.area.id, client.get_char_name(), message), client)

def ooc_cmd_bloodtrail_list(client, arg):
    """ (STAFF ONLY)
    Lists all areas that contain non-empty blood trails and how those look like.

    SYNTAX
    /bloodtrail_list

    PARAMETERS
    None

    EXAMPLE
    /bloodtrail_list
    """

    Constants.command_assert(client, arg, is_staff=True, parameters='=0')

    # Get all areas with blood in them
    areas = sorted([area for area in client.server.area_manager.areas if len(area.bleeds_to) > 0 or
                    area.blood_smeared], key=lambda x: x.name)

    # No areas found means there are no blood trails
    if not areas:
        raise ClientError('No areas have blood.')

    # Otherwise, build the list of all areas with blood
    info = '== Blood trails in this server =='
    for area in areas:
        area_bleeds_to = sorted(area.bleeds_to)

        if area_bleeds_to == [area.name]:
            pre_info = area.name
        else:
            area_bleeds_to.remove(area.name)
            pre_info = ", ".join(area_bleeds_to)

        if area.blood_smeared:
            pre_info += ' (SMEARED)'

        info += '\r\n*({}) {}: {}'.format(area.id, area.name, pre_info)

    client.send_ooc(info)

def ooc_cmd_bloodtrail_set(client, arg):
    """ (STAFF ONLY)
    Sets (and replaces!) the blood trail of the current area to link all relevant areas by ID or
    name separated by commas. If not given any areas, it will set the blood trail to be a single
    unconnected pool of blood in the area.
    Requires /bloodtrail_clean to undo.

    SYNTAX
    /bloodtrail_set {area_1}, {area_2}, ....

    OPTIONAL PARAMETERS
    {area_n}: Area ID or name

    EXAMPLE
    Assuming the player is in area 0
    /bloodtrail_set                           :: Sets the blood trail in area 0 to be a single pool of blood
    /bloodtrail_set 3, Class Trial Room,\ 2   :: Sets the blood trail in area 0 to go to area 3 and Class Trial Room, 2 (note the ,\).

    NOTE: This command will automatically add the current area to the blood trail if not explicitly
    included, as it does not make too much physical sense to have a trail lead out of an area
    while there being no blood in the current area.
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')

    if not arg:
        areas_to_link = [client.area]
        message = 'be an unconnected pool of blood'
    else:
        # Make sure the input is valid before starting
        raw_areas_to_link = arg.split(", ")
        areas_to_link = set(Constants.parse_area_names(client, raw_areas_to_link) + [client.area])
        message = 'go to {}'.format(Constants.cjoin([a.name for a in areas_to_link], the=True))

    client.send_ooc('Set the blood trail in this area to {}.'.format(message))
    client.send_ooc_others('The blood trail in this area was set to {}.'.format(message),
                           is_staff=False, in_area=True, to_blind=False)
    client.send_ooc_others('(X) {} set the blood trail in area {} to {}.'
                           .format(client.name, client.area.name, message), is_staff=True)
    client.area.bleeds_to = {area.name for area in areas_to_link}

def ooc_cmd_bloodtrail_smear(client, arg):
    """
    Smears the blood trails of the current area or (STAFF ONLY) given areas by ID or name separated
    by commas. If not given any areas, it will smear the blood trail of the current area.
    As long as the area has smeared blood, no new blood trails will be recorded and any visual
    indication of preexisting blood trails will be replaced with a 'Smeared' indication for
    non-staff members.
    Returns an error if the area has no blood or its blood is already smeared.

    SYNTAX
    /bloodtrail_smear {area_1}, {area_2}, ....

    OPTIONAL PARAMETERS
    {area_n}: Area ID or name

    EXAMPLE
    Assuming the player is in area 0
    /bloodtrail_smear                           :: Smears the blood trail in area 0
    /bloodtrail_smear 3, Class Trial Room,\ 2   :: Smears the blood trail in area 3 and Class Trial Room, 2 (note the ,\)
    """

    if not arg:
        areas_to_smear = [client.area]
    else:
        if not client.is_staff():
            raise ClientError('You must be authorized to do that.')
        # Make sure the input is valid before starting
        raw_areas_to_smear = arg.split(", ")
        areas_to_smear = set(Constants.parse_area_names(client, raw_areas_to_smear))

    successful_smears = set()
    for area in areas_to_smear:
        if not area.bleeds_to and not client.is_staff():
            if not arg:
                mes = 'You could not find any blood in the area.'
            else:
                mes = 'There is no blood in area {}.'.format(area.name)
            client.send_ooc(mes)
            continue
        elif area.blood_smeared:
            client.send_ooc('Area {} already has its blood trails smeared.'.format(area.name))
        else:
            client.send_ooc_others('{} smeared the blood trail in your area.'
                                   .format(client.displayname), is_staff=False,
                                   in_area=area, to_blind=False, pred=lambda c: area.lights)
            area.blood_smeared = True
            successful_smears.add(area.name)

    if successful_smears:
        if not arg:
            aname1 = 'your area'
            aname2 = 'area {}'.format(client.area.name)

            message = client.area.name
            client.send_ooc("You smeared the blood trail in your area.")
            connector = '(X) ' if not client.area.lights else ''

            if client.is_staff():
                name = client.name
            else:
                name = client.displayname

            mes = '{}{} smeared the blood trail in {}.'
            client.send_ooc_others(mes.format(connector, name, aname1), is_staff=True, in_area=True)
            client.send_ooc_others(mes.format('(X) ', name, aname2), is_staff=True, in_area=False)
        elif len(successful_smears) == 1:
            message = str(successful_smears.pop())
            client.send_ooc("You smeared the blood trail in area {}.".format(message))
            client.send_ooc_others('(X) {} smeared the blood trail in area {}.'
                                   .format(client.name, message), is_staff=True)
        elif len(successful_smears) > 1:
            message = Constants.cjoin(successful_smears)
            client.send_ooc("You smeared the blood trails in areas {}.".format(message))
            client.send_ooc_others('(X) {} smeared the blood trails in areas {}.'
                                   .format(client.name, message), is_staff=True)
        logger.log_server('[{}][{}]Smeared the blood trail in {}.'
                          .format(client.area.id, client.get_char_name(), message), client)

def ooc_cmd_can_iniswap(client, arg):
    """ (MOD ONLY)
    Toggles iniswapping by non-staff in the current area being allowed/disallowed.

    SYNTAX
    /can_iniswap

    PARAMETERS
    None

    EXAMPLES
    /can_iniswap
    """

    if not client.is_mod:
        raise ClientError('You must be authorized to do that.')
    if len(arg) != 0:
        raise ArgumentError('This command takes no arguments.')

    status = {True: 'now', False: 'no longer'}
    client.area.iniswap_allowed = not client.area.iniswap_allowed

    client.area.broadcast_ooc('Iniswapping is {} allowed in this area.'
                              .format(status[client.area.iniswap_allowed]))
    logger.log_server('[{}][{}]Set iniswapping as {} allowed in the area.'
                      .format(client.area.id, client.get_char_name(),
                              status[client.area.iniswap_allowed]), client)

def ooc_cmd_can_passagelock(client, arg):
    """ (STAFF ONLY)
    Toggles the ability of using /unilock and /bilock for non-staff members in the current area.
    In particular, the area cannot be used as an argument either implicitly or explicitly in
    /bilock, or implicitly in /unilock if ability is turned off (but can be used explicitly).

    SYNTAX
    /toggle_passagelock

    PARAMETERS
    None

    EXAMPLE
    Assuming the current area started allowing the use of both commands...
    /can_passagelock         :: Non-staff members can no longer use /bilock or /unilock.
    /can_passagelock         :: Non-staff members can now use /bilock and /unilock again.
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')
    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    client.area.change_reachability_allowed = not client.area.change_reachability_allowed
    status = {True: 'enabled', False: 'disabled'}

    client.area.broadcast_ooc('A staff member has {} the use of /unilock or /bilock that '
                              'affect this area.'
                              .format(status[client.area.change_reachability_allowed]))

def ooc_cmd_can_rollp(client, arg):
    """ (STAFF ONLY)
    Toggles private rolls by non-staff in the current area being allowed/disallowed.

    SYNTAX
    /can_rollp

    PARAMETERS
    None

    EXAMPLES
    /can_rollp
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')
    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    client.area.rollp_allowed = not client.area.rollp_allowed
    status = {False: 'disabled', True: 'enabled'}

    client.area.broadcast_ooc('A staff member has {} the use of private roll commands in this '
                              'area.'.format(status[client.area.rollp_allowed]))
    logger.log_server('[{}][{}]{} private roll commands in this area.'
                      .format(client.area.id, client.get_char_name(),
                              status[client.area.rollp_allowed].capitalize()), client)

def ooc_cmd_can_rpgetarea(client, arg):
    """ (STAFF ONLY)
    Toggles users subject to RP mode being able/unable to use /getarea in the current area.

    SYNTAX
    /can_rpgetarea

    PARAMETERS
    None

    EXAMPLE
    /can_rpgetarea
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')
    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    client.area.rp_getarea_allowed = not client.area.rp_getarea_allowed
    status = {False: 'disabled', True: 'enabled'}

    client.area.broadcast_ooc('A staff member has {} the use of /getarea in this area.'
                              .format(status[client.area.rp_getarea_allowed]))
    logger.log_server('[{}][{}]{} /getarea in this area.'
                      .format(client.area.id, client.get_char_name(),
                              status[client.area.rp_getarea_allowed].capitalize()), client)

def ooc_cmd_can_rpgetareas(client, arg):
    """ (STAFF ONLY)
    Toggles users subject to RP mode being able/unable to use /getareas in the current area.

    SYNTAX
    /can_rpgetareas

    PARAMETERS
    None

    EXAMPLE
    /can_rpgetareas
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')
    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    client.area.rp_getareas_allowed = not client.area.rp_getareas_allowed
    status = {False: 'disabled', True: 'enabled'}

    client.area.broadcast_ooc('A staff member has {} the use of /getareas in this area.'
                              .format(status[client.area.rp_getareas_allowed]))
    logger.log_server('[{}][{}]{} /getareas in this area.'
                      .format(client.area.id, client.get_char_name(),
                              status[client.area.rp_getareas_allowed].capitalize()), client)

def ooc_cmd_charselect(client, arg):
    """
    Opens the character selection screen for the current user
    OR (MOD ONLY) forces another user by identifier to have that screen open, freeing up their
    character in the process.

    SYNTAX
    /charselect
    /charselect {client_id}
    /charselect {client_ipid}

    PARAMETERS
    {client_id}: Client identifier (number in brackets in /getarea).
    {client_ipid}: IPID for the client (number in parentheses in /getarea).

    EXAMPLES
    /charselect                    :: Open character selection screen for the current user.
    /charselect 1                  :: Forces open the character selection screen for the user whose client ID is 1
    /charselect 1234567890         :: Forces open the character selection screen for the user whose IPID is 1234567890
    """

    # Open for current user case
    if not arg:
        client.char_select()

    # Force open for different user
    else:
        if not client.is_mod:
            raise ClientError('You must be authorized to do that.')

        for c in Constants.parse_id_or_ipid(client, arg):
            c.char_select()

def ooc_cmd_char_restrict(client, arg):
    """ (STAFF ONLY)
    Toggle a character by folder name (not showname!) being able to be used in the current area
    by non-staff members.
    Returns an error if the character name is not recognized.

    SYNTAX
    /char_restrict <char_name>

    PARAMETERS
    <char_name>: Character name to restrict.

    EXAMPLES
    Assuming Phantom_HD is initially unrestricted....
    /char_restrict Phantom_HD           :: Restrict the use of Phantom_HD.
    /char_restrict Phantom_HD           :: Unrestrict the use of Phantom_HD.
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')
    if len(arg) == 0:
        raise ArgumentError('This command takes one character name.')

    if arg not in client.server.char_list:
        raise ArgumentError('Unrecognized character folder name: {}'.format(arg))

    status = {True: 'enabled', False: 'disabled'}
    client.area.broadcast_ooc('A staff member has {} the use of character {} in this area.'
                              .format(status[arg in client.area.restricted_chars], arg))

    # If intended character not in area's restriction, add it
    if arg not in client.area.restricted_chars:
        client.area.restricted_chars.add(arg)
        # For all clients using the now restricted character, switch them to some other character.
        for c in client.area.clients:
            if not c.is_staff() and c.get_char_name() == arg:
                try:
                    new_char_id = c.area.get_rand_avail_char_id(allow_restricted=False)
                except AreaError:
                    # Force into spectator mode if all other available characters are taken
                    new_char_id = -1
                c.change_character(new_char_id)
                c.send_ooc('Your character has been set to restricted in this area by a staff '
                           'member. Switching you to {}.'.format(c.get_char_name()))
    else:
        client.area.restricted_chars.remove(arg)

def ooc_cmd_chars_restricted(client, arg):
    """
    Returns a list of all characters that are restricted in an area.

    SYNTAX
    /chars_restricted

    PARAMETERS
    None

    EXAMPLES
    If only Phantom_HD is restricted in the current area...
    /chars_restricted           :: Returns 'Phantom_HD'
    """

    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    info = '== Characters restricted in area {} =='.format(client.area.name)
    # If no characters restricted, print a manual message.
    if len(client.area.restricted_chars) == 0:
        info += '\r\n*No characters restricted.'
    # Otherwise, build the list of all restricted chars.
    else:
        for char_name in client.area.restricted_chars:
            info += '\r\n*{}'.format(char_name)

    client.send_ooc(info)

def ooc_cmd_cleardoc(client, arg):
    """
    Clears the current area's doc.

    SYNTAX
    /cleardoc

    PARAMETERS
    None

    EXAMPLES
    /cleardoc
    """

    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    client.area.broadcast_ooc('{} cleared the doc link.'.format(client.displayname))
    logger.log_server('[{}][{}]Cleared document. Old link: {}'
                      .format(client.area.id, client.get_char_name(), client.area.doc), client)
    client.area.change_doc()

def ooc_cmd_cleargm(client, arg):
    """ (CM AND MOD ONLY)
    Logs out all game masters in the server and puts them in RP mode if needed.

    SYNTAX
    /cleargm

    PARAMETERS
    None

    EXAMPLE
    /cleargm
    """

    if not client.is_mod and not client.is_cm:
        raise ClientError('You must be authorized to do that.')
    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    for area in client.server.area_manager.areas:
        for c in [x for x in area.clients if x.is_gm]:
            c.is_gm = False
            if client.server.rp_mode:
                c.in_rp = True
            # Update the music list to show reachable areas and activate the AFK timer
            c.reload_music_list()
            c.server.create_task(client, ['as_afk_kick', client.area.afk_delay, client.area.afk_sendto])

            c.send_ooc('You are no longer a GM.')
    client.send_ooc('All GMs logged out.')

def ooc_cmd_clock(client, arg):
    """ (STAFF ONLY)
    Sets up a day cycle that will tick one hour every given number of seconds and provide a time
    announcement to a given range of areas. Starting hour is also given. The clock ID is by default
    the client ID of the player who started the clock. Doing /clock while running an active clock
    will silently overwrite the old clock with the new one.
    Requires /clock_cancel to undo.

    SYNTAX
    /clock <area_range_start> <area_range_end> <hour_length> <hour_start>

    PARAMETERS
    <area_range_start>: Send notifications from this area onwards up to...
    <area_range_end>: Send notifications up to (and including) this area.
    <hour_length>: Length of each ingame hour (in seconds)
    <hour_start>: Starting hour (integer from 0 to 23)

    EXAMPLES
    /clock 16 116 900 8         :: Start a 900-second hour clock spanning areas 16 through 116, with starting hour 8 a.m.
    /clock 0 5 10 19            :: Start a 10-second hour clock spanning areas 0 through 5, with starting hour 7 p.m.
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')

    # Perform input validation first
    try:
        pre_area_1, pre_area_2, pre_hour_length, pre_hour_start = arg.split(' ')
    except ValueError:
        raise ClientError('This command takes four arguments.')

    areas = Constants.parse_two_area_names(client, [pre_area_1, pre_area_2], check_valid_range=True)
    area_1, area_2 = areas[0].id, areas[1].id

    try:
        hour_length = int(pre_hour_length)
        if hour_length <= 0:
            raise ValueError
    except ValueError:
        raise ArgumentError('Invalid hour length {}.'.format(pre_hour_length))

    try:
        hour_start = int(pre_hour_start)
        if hour_start < 0 or hour_start >= 24:
            raise ValueError
    except ValueError:
        raise ArgumentError('Invalid hour start {}.'.format(pre_hour_start))

    # Code after this assumes input is validated
    try:
        client.server.get_task(client, ['as_day_cycle'])
    except KeyError:
        normie_notif = True
    else:
        # Already existing day cycle. Will overwrite preexisting one
        # But first, make sure normies do not get a new notification.
        normie_notif = False

    client.send_ooc('You initiated a day cycle of length {} seconds per hour in areas {} through '
                    '{}. The cycle ID is {}.'.format(hour_length, area_1, area_2, client.id))
    client.send_ooc_others('(X) {} initiated a day cycle of length {} seconds per hour in areas {} '
                           'through {}. The cycle ID is {} ({}).'
                           .format(client.name, hour_length, area_1, area_2, client.id,
                                   client.area.id), is_staff=True)
    if normie_notif:
        client.send_ooc_others('{} initiated a day cycle.'.format(client.displayname),
                               is_staff=False, pred=lambda c: area_1 <= c.area.id <= area_2)

    client.server.create_task(client, ['as_day_cycle', time.time(), area_1, area_2, hour_length,
                                       hour_start, normie_notif])

def ooc_cmd_clock_cancel(client, arg):
    """ (STAFF ONLY)
    Cancel the day cycle established by a player by client ID (or own if not given ID)
    Returns an error if the given player has no associated active day cycle.

    SYNTAX
    /clock_cancel {client_id}

    OPTIONAL PARAMETERS
    {client_id}: Client identifier (number in brackets in /getarea)

    EXAMPLE
    /clock_cancel 0         :: Cancels the day cycle established by the player whose client ID is 0.
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')
    if len(arg) == 0:
        arg = str(client.id)

    try:
        c = Constants.parse_id(client, arg)
    except ClientError:
        raise ArgumentError('Client {} is not online.'.format(arg))

    try:
        client.server.remove_task(c, ['as_day_cycle'])
    except KeyError:
        raise ClientError('Client {} has not initiated any day cycles.'.format(arg))

def ooc_cmd_clock_pause(client, arg):
    """ (STAFF ONLY)
    Pauses the day cycle established by a player by client ID (or own if not given an ID).
    Requires /clock_unpause to undo.
    Returns an error if the given player has no associated active day cycle, or if their day cycle
    is already paused.

    SYNTAX
    /clock_pause {client_id}

    OPTIONAL PARAMETERS
    {client_id}: Client identifier (number in brackets in /getarea)

    EXAMPLE
    /clock_pause 0         :: Pauses the day cycle established by the player whose client ID is 0.
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')
    if len(arg) == 0:
        arg = str(client.id)

    try:
        c = Constants.parse_id(client, arg)
    except ClientError:
        raise ArgumentError('Client {} is not online.'.format(arg))

    try:
        task = client.server.get_task(c, ['as_day_cycle'])
    except KeyError:
        raise ClientError('Client {} has not initiated any day cycles.'.format(arg))

    is_paused = client.server.get_task_attr(c, ['as_day_cycle'], 'is_paused')
    if is_paused:
        raise ClientError('Day cycle is already paused.')

    client.server.set_task_attr(c, ['as_day_cycle'], 'is_paused', True)
    client.server.cancel_task(task)

def ooc_cmd_clock_unpause(client, arg):
    """ (STAFF ONLY)
    Unpauses the day cycle established by a player by client ID (or own if not given an ID).
    Requires /clock_pause to undo.
    Returns an error if the given player has no associated active day cycle, or if their day cycle
    is already unpaused.

    SYNTAX
    /clock_unpause {client_id}

    OPTIONAL PARAMETERS
    {client_id}: Client identifier (number in brackets in /getarea)

    EXAMPLE
    /clock_unpause 0         :: Unpauses the day cycle established by the player whose client ID is 0.
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')
    if len(arg) == 0:
        arg = str(client.id)

    try:
        c = Constants.parse_id(client, arg)
    except ClientError:
        raise ArgumentError('Client {} is not online.'.format(arg))

    try:
        client.server.get_task(c, ['as_day_cycle'])
    except KeyError:
        raise ClientError('Client {} has not initiated any day cycles.'.format(arg))

    is_paused = client.server.get_task_attr(c, ['as_day_cycle'], 'is_paused')
    if not is_paused:
        raise ClientError('Day cycle is already unpaused.')

    client.server.set_task_attr(c, ['as_day_cycle'], 'is_paused', False)
    client.server.set_task_attr(c, ['as_day_cycle'], 'just_unpaused', True)

def ooc_cmd_coinflip(client, arg):
    """
    Flips a coin and returns the result.

    SYNTAX
    /coinflip

    PARAMETERS
    None

    EXAMPLES
    /coinflip
    """

    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    coin = ['heads', 'tails']
    flip = random.choice(coin)
    client.area.broadcast_ooc('{} flipped a coin and got {}.'.format(client.displayname, flip))
    logger.log_server('[{}][{}]Used /coinflip and got {}.'
                      .format(client.area.id, client.get_char_name(), flip), client)

def ooc_cmd_currentmusic(client, arg):
    """
    Returns the music currently playing and who played it, or None if no music is playing.

    SYNTAX
    /currentmusic

    PARAMETERS
    None

    EXAMPLES
    /currentmusic
    """

    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    if client.area.current_music == '':
        raise ClientError('There is no music currently playing.')
    client.send_ooc('The current music is {} and was played by {}.'
                    .format(client.area.current_music, client.area.current_music_player))

def ooc_cmd_deafen(client, arg):
    """ (STAFF ONLY)
    Changes the deafened status of a player by client ID.
    Deaf players will be unable to read IC messages properly or receive other audio cues from
    commands such as /knock, /scream, etc.
    Immediately after deafening/undeafening, the target will receive sense-appropiate blood
    notifications in the area if needed (e.g. players bleeding while sneaking).
    Returns an error if the given identifier does not correspond to a user.

    SYNTAX
    /deafen <client_id>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)

    EXAMPLES
    Assuming client 1 starts hearing...
    /deafen 1            :: Deafens client 1
    /deafen 1            :: Undeafens client 1
    """

    Constants.command_assert(client, arg, is_staff=True)
    target = Constants.parse_id(client, arg)

    status = {False: 'undeafened', True: 'deafened'}
    target.is_deaf = not target.is_deaf

    client.send_ooc('You have {} {}.'.format(status[target.is_deaf], target.displayname))
    target.send_ooc('You have been {}.'.format(status[target.is_deaf]))
    target.send_ooc_others('(X) {} has {} {} ({}).'
                           .format(client.name, status[target.is_deaf], target.displayname,
                                   target.area.id), is_staff=True, not_to={client})

    target.area_changer.notify_me_blood(target.area, changed_visibility=False, changed_hearing=True)

def ooc_cmd_defaultarea(client, arg):
    """ (MOD ONLY)
    Set the default area by area ID for all future clients to join when connecting to the server.
    Returns an error if the area ID is invalid.

    SYNTAX
    /defaultarea <area_id>

    PARAMETERS
    <area_id>: Intended default area ID

    EXAMPLES
    /defaultarea 1          :: Set area 1 to be the default area.
    """

    if not client.is_mod:
        raise ClientError('You must be authorized to do that.')
    if len(arg) == 0:
        raise ClientError('This command takes one argument.')

    try:
        client.server.area_manager.get_area_by_id(int(arg))
    except ValueError:
        raise ArgumentError('Expected numerical value for area ID.')
    except AreaError:
        raise ClientError('ID {} does not correspond to a valid area ID.'.format(arg))

    client.server.default_area = int(arg)
    client.send_ooc('Set default area to {}'.format(arg))

def ooc_cmd_discord(client, arg):
    """
    Returns the server's Discord server invite link.

    SYNTAX
    /discord

    PARAMETERS
    None

    EXAMPLE
    /discord            :: Sends the Discord invite link
    """

    Constants.command_assert(client, arg, parameters='=0')

    client.send_ooc('Discord Invite Link: {}'.format(client.server.config['discord_link']))

def ooc_cmd_disemconsonant(client, arg):
    """ (MOD ONLY)
    Disemconsonants all IC and OOC messages of a player by client ID (number in brackets) or IPID
    (number in parentheses). In particular, all their messages will have all their consonants
    removed. If given IPID, it will affect all clients opened by the user. Otherwise, it will just
    affect the given client. Requires /undisemconsonant to undo.
    Returns an error if the given identifier does not correspond to a user.

    SYNTAX
    /disemconsonant <client_id>
    /disemconsonant <client_ipid>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)
    <client_ipid>: IPID for the client (number in parentheses in /getarea)

    EXAMPLES
    /disemconsonant 1           :: Disemconsonants the player whose client ID is 1.
    /disemconsonant 1234567890  :: Disemconsonants all clients opened by the user whose IPID is 1234567890.
    """

    if not client.is_mod:
        raise ClientError('You must be authorized to do that.')

    # Disemconsonant matching targets
    for c in Constants.parse_id_or_ipid(client, arg):
        c.disemconsonant = True
        logger.log_server('Disemconsonanted {}.'.format(c.ipid), client)
        client.area.broadcast_ooc("{} was disemconsonanted.".format(c.displayname))

def ooc_cmd_disemvowel(client, arg):
    """ (MOD ONLY)
    Disemvowels all IC and OOC messages of a player by client ID (number in brackets) or IPID
    (number in parentheses). In particular, all their messages will have all their vowels removed.
    If given IPID, it will affect all clients opened by the user. Otherwise, it will just affect
    the given client. Requires /undisemvowel to undo.
    Returns an error if the given identifier does not correspond to a user.

    SYNTAX
    /disemvowel <client_id>
    /disemvowel <client_ipid>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)
    <client_ipid>: IPID for the client (number in parentheses in /getarea)

    EXAMPLES
    /disemvowel 1                     :: Disemvowels the player whose client ID is 1.
    /disemvowel 1234567890            :: Disemwvowels all clients opened by the user whose IPID is 1234567890.
    """

    if not client.is_mod:
        raise ClientError('You must be authorized to do that.')

    # Disemvowel matching targets
    for c in Constants.parse_id_or_ipid(client, arg):
        c.disemvowel = True
        logger.log_server('Disemvowelled {}.'.format(c.ipid), client)
        client.area.broadcast_ooc("{} was disemvowelled.".format(c.displayname))

def ooc_cmd_doc(client, arg):
    """
    Sends the area's current doc link to the user, or sets it to a new one.

    SYNTAX
    /doc {doc_link}

    PARAMETERS
    {doc_link}: Link to new document.

    EXAMPLES
    /doc https://www.google.com     :: Sets the document link to the Google homepage.
    /doc                            :: Returns the current document (e.g. https://www.google.com)
    """

    # Clear doc case
    if len(arg) == 0:
        client.send_ooc('Document: {}'.format(client.area.doc))
        logger.log_server('[{}][{}]Requested document. Link: {}'
                          .format(client.area.id, client.get_char_name(), client.area.doc), client)
    # Set new doc case
    else:
        client.area.change_doc(arg)
        client.area.broadcast_ooc('{} changed the doc link.'.format(client.displayname))
        logger.log_server('[{}][{}]Changed document to: {}'
                          .format(client.area.id, client.get_char_name(), arg), client)

def ooc_cmd_follow(client, arg):
    """ (STAFF ONLY)
    Starts following a player by their client ID. When the target area moves area, you will follow
    them automatically except if disallowed by the new area.
    Requires /unfollow to undo.
    Returns an error if the client is part of a party.

    SYNTAX
    /follow <client_id>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)

    EXAMPLE
    /follow 1                     :: Starts following the player whose client ID is 1
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')
    if client.party:
        raise PartyError('You cannot follow someone while in a party.')

    c = Constants.parse_id(client, arg)
    client.follow_user(c)
    logger.log_server('{} began following {}.'
                      .format(client.get_char_name(), c.get_char_name()), client)

def ooc_cmd_g(client, arg):
    """
    Sends a global message in the OOC chat visible to all users in the server who have not disabled
    global chat. Returns an error if the user has global chat off or sends an empty message.

    SYNTAX
    /g <message>

    PARAMETERS
    <message>: Message to be sent

    EXAMPLE
    /g Hello World      :: Sends Hello World to global chat.
    """

    if client.muted_global:
        raise ClientError('You have the global chat muted.')
    if len(arg) == 0:
        raise ArgumentError("You cannot send an empty message.")

    client.server.broadcast_global(client, arg)
    logger.log_server('[{}][{}][GLOBAL]{}.'
                      .format(client.area.id, client.get_char_name(), arg), client)

def ooc_cmd_gag(client, arg):
    """ (STAFF ONLY)
    Changes the gagged status of a player by client ID.
    Gagged players will be unable to talk IC properly or use other talking features such as /scream.
    Returns an error if the given identifier does not correspond to a user.

    SYNTAX
    /gag <client_id>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)

    EXAMPLES
    Assuming client 1 starts hearing...
    /gag 1            :: Gags client 1
    /gag 1            :: Ungags client 1
    """

    Constants.command_assert(client, arg, is_staff=True)
    target = Constants.parse_id(client, arg)

    status = {False: 'ungagged', True: 'gagged'}
    target.is_gagged = not target.is_gagged

    client.send_ooc('You have {} {}.'.format(status[target.is_gagged], target.displayname))
    target.send_ooc('You have been {}.'.format(status[target.is_gagged]))
    target.send_ooc_others('(X) {} has {} {} ({}).'
                           .format(client.name, status[target.is_gagged], target.displayname,
                                   target.area.id), is_staff=True, not_to={client})

def ooc_cmd_getarea(client, arg):
    """
    List the characters (and associated client IDs) in the current area.
    Returns an error if the user is subject to RP mode and is in an area that disables /getarea, or
    if they are blind and not staff.

    SYNTAX
    /getarea

    PARAMETERS
    None

    EXAMPLE
    /getarea
    """

    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')
    if not client.is_staff() and client.is_blind:
        raise ClientError('You are blind, so you cannot see anything.')

    client.send_area_info(client.area, client.area.id, False)

def ooc_cmd_getareas(client, arg):
    """
    List the characters (and associated client IDs) in each area.
    Returns an error if the user is subject to RP mode and is in an area that disables /getareas,
    or if they are blind and not staff.

    SYNTAX
    /getareas

    PARAMETERS
    None

    EXAMPLE
    /getareas
    """

    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')
    if not client.is_staff() and client.is_blind:
        raise ClientError('You are blind, so you cannot see anything.')

    client.send_area_info(client.area, -1, False)

def ooc_cmd_gimp(client, arg):
    """ (MOD ONLY)
    Gimps all IC messages of a player by client ID (number in brackets) or IPID (number in
    parentheses). In particular, their message will be replaced by one of the messages listed in
    Constants.gimp_message in Constants.py. If given IPID, it will affect all clients opened by the
    user. Otherwise, it will just affect the given client. Requires /ungimp to undo.
    Returns an error if the given identifier does not correspond to a user.

    SYNTAX
    /gimp <client_id>
    /gimp <client_ipid>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)
    <client_ipid>: IPID for the client (number in parentheses in /getarea)

    EXAMPLES
    /gimp 1                     :: Gimps the player whose client ID is 1.
    /gimp 1234567890            :: Gimps all clients opened by the user whose IPID is 1234567890.
    """

    if not client.is_mod:
        raise ClientError('You must be authorized to do that.')

    # Gimp matching targets
    for c in Constants.parse_id_or_ipid(client, arg):
        c.gimp = True
        logger.log_server('Gimping {}.'.format(c.ipid), client)
        client.area.broadcast_ooc("{} was gimped.".format(c.displayname))

def ooc_cmd_globalic(client, arg):
    """ (STAFF ONLY)
    Send client's subsequent IC messages to users only in specified areas. Can take either area IDs
    or area names. If current user is not in intended destination range, it will NOT send messages
    to their area. Requires /unglobalic to undo.

    If given two areas, it will send the IC messages to all areas between the given ones inclusive.
    If given one area, it will send the IC messages only to the given area.

    SYNTAX
    /globalic <target_area>
    /globalic <area_range_start>, <area_range_end>

    PARAMETERS
    <target_area>: Send IC messages just to this area.

    <area_range_start>: Send IC messages from this area onwards up to...
    <area_range_end>: Send IC messages up to (and including) this area.

    EXAMPLES
    /globalic 1, Courtroom 3                :: Send IC messages to areas 1 through "Courtroom 3" (if client in area 0, they will not see their own message).
    /globalic 3                             :: Send IC messages just to area 3.
    /globalic 1, 1                          :: Send IC messages just to area 1.
    /globalic Courtroom,\ 2, Courtroom 3    :: Send IC messages to areas "Courtroom, 2" through "Courtroom 3" (note the escape character).
    """

    Constants.command_assert(client, arg, parameters='&1-2', is_staff=True, split_commas=True)
    areas = Constants.parse_two_area_names(client, arg.split(', '))

    client.multi_ic = areas

    if areas[0] == areas[1]:
        client.send_ooc('Your IC messages will now be sent to area {}.'.format(areas[0].name))
    else:
        client.send_ooc('Your IC messages will now be sent to areas {} through {}.'
                        .format(areas[0].name, areas[1].name))

def ooc_cmd_globalic_pre(client, arg):
    """ (STAFF ONLY)
    If given an argument, it sets the client's message prefix that must be included in their IC
    messages in order for them to be globally sent as part of a /globalic command. Messages that
    do not start with this prefix will only be sent to their current area as usual. This prefix
    will also be filtered out from their message.
    If given nothing, it removes the prefix requirement and all messages will be sent globally if
    /globalic is on.

    SYNTAX
    /globalic_pre {prefix}

    OPTIONAL PARAMETERS
    {prefix}: Message prefix

    EXAMPLES
    Assuming /globalic is on...
    /globalic_pre >>>       :: Only IC messages that start with >>> will be sent globally-
    /globalic_pre           :: All IC messages will be sent globally.
    """

    Constants.command_assert(client, arg, is_staff=True)

    client.multi_ic_pre = arg
    if arg:
        client.send_ooc('You have set your global IC prefix to {}'.format(arg))
    else:
        client.send_ooc('You have removed your global IC prefix.')

def ooc_cmd_gm(client, arg):
    """ (MOD ONLY)
    Similar to /g, but with the following changes:
    *Includes a "[GLOBAL-MOD]" tag to the message to indicate a mod sent the message.
    *Uses the OOC username as opposed to the character name when displaying the message.
    Returns an error if the user has global chat off or sends an empty message.

    SYNTAX
    /gm <message>

    PARAMETERS
    <message>: Message to be sent

    EXAMPLE
    /gm Hello World     :: Sends Hello World to globat chat, preceded with [GLOBAL-MOD].
    """

    try:
        Constants.command_assert(client, arg, is_mod=True, parameters='>0')
    except ArgumentError:
        raise ArgumentError("You cannot send an empty message.")

    if client.muted_global:
        raise ClientError('You have the global chat muted.')

    client.server.broadcast_global(client, arg, True)
    logger.log_server('[{}][{}][GLOBAL-MOD]{}.'
                      .format(client.area.id, client.get_char_name(), arg), client)

def ooc_cmd_gmlock(client, arg):
    """ (STAFF ONLY)
    Sets the current area as accessible only to staff members. Players in the area at the time of
    the lock will be able to leave and return to the area, regardless of authorization.
    Requires /unlock to undo.
    Returns an error if the area is already gm-locked or if the area is set to be unlockable.

    SYNTAX
    /gmlock

    PARAMETERS
    None

    EXAMPLE
    /gmlock             :: Sets the current area as accessible only to staff members.
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')
    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    if not client.area.locking_allowed:
        raise ClientError('Area locking is disabled in this area.')
    if client.area.is_gmlocked:
        raise ClientError('Area is already gm-locked.')

    client.area.is_gmlocked = True
    client.area.broadcast_ooc('Area gm-locked.')
    for i in client.area.clients:
        client.area.invite_list[i.ipid] = None

def ooc_cmd_handicap(client, arg):
    """ (STAFF ONLY)
    Sets a movement handicap on a client by ID or IPID so that they need to wait a set amount of
    time between changing areas. This will override any previous handicaps the client(s) may have
    had, including custom ones and server ones (such as through sneak). Server handicaps will
    override custom handicaps if the server handicap is longer. However, as soon as the server
    handicap is over, it will recover the old custom handicap.
    If given IPID, it will set the movement handicap on all the clients opened by the user.
    Otherwise, it will just do it to the given client.
    Requires /unhandicap to undo.
    Returns an error if the given identifier does not correspond to a user, or if given a
    non-positive length of time.

    SYNTAX
    /handicap <client_id> <length> {name} {announce_if_over}
    /handicap <client_ipid> <length> {name} {announce_if_over}

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)
    <client_ipid>: IPID for the client (number in parentheses in /getarea)
    <length>: Handicap length (in seconds)

    OPTIONAL PARAMETERS
    {name}: Name of the handicap (e.g. "Injured", "Sleepy", etc.). By default it is "Handicap".
    {announce_if_over}: If the server will send a notification once the player may move areas after
    waiting for their handicap timer. By default it is true. For the server not to send them, put
    one of these keywords: False, false, 0, No, no

    EXAMPLES
    /handicap 0 5                   :: Sets a 5 second movement handicap on the player whose client ID is 0.
    /handicap 1234567890 10 Injured :: Sets a 10 second movement handicap called "Injured" on the clients whose IPID is 1234567890.
    /handicap 1 15 StabWound False  :: Sets a 15 second movement handicap called "StabWound" on the player whose client ID is 0
    which will not send notifications once the timer expires.
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')

    args = arg.split(' ')
    if len(args) < 2:
        raise ClientError('This command variation takes at least two parameters '
                          '(target and length).')
    if len(args) >= 5:
        raise ClientError('This command variation takes at most four parameters '
                          '(target, length, name, announce_if_over).')

    # Obtain targets
    targets = Constants.parse_id_or_ipid(client, args[0])

    # Check if valid length and convert to seconds
    length = Constants.parse_time_length(args[1]) # Also internally validates

    # Check name
    if len(args) >= 3:
        name = args[2]
    else:
        name = "Handicap" # No spaces!

    # Check announce_if_over status
    if len(args) >= 4 and args[3] in ['False', 'false', '0', 'No', 'no']:
        announce_if_over = False
    else:
        announce_if_over = True

    for c in targets:
        client.send_ooc('You imposed a movement handicap "{}" of length {} seconds on {}.'
                        .format(name, length, c.displayname))
        msg = ('(X) {} imposed a movement handicap "{}" of length {} seconds on {} in area {} ({}).'
               .format(client.name, name, length, c.displayname, client.area.name,
                       client.area.id))
        client.send_ooc_others(msg, is_staff=True, pred=lambda x: x != c)
        c.send_ooc('You were imposed a movement handicap "{}" of length {} seconds when '
                   'changing areas.'.format(name, length))

        client.server.create_task(c, ['as_handicap', time.time(), length, name, announce_if_over])
        c.handicap_backup = (client.server.get_task(c, ['as_handicap']),
                             client.server.get_task_args(c, ['as_handicap']))

def ooc_cmd_help(client, arg):
    """
    Returns the website with all available commands and their instructions (usually a GitHub
    repository).

    SYNTAX
    /help

    PARAMETERS
    None

    EXAMPLES
    /help
    """

    if not arg:
        url = 'https://github.com/Chrezm/TsuserverDR'
        help_msg = 'Available commands, source code and issues can be found here: {}'.format(url)
        client.send_ooc(help_msg)
        return

    ranks_to_try = [
            ('normie', True),
            ('gm', client.is_staff()),
            ('cm', client.is_mod or client.is_cm),
            ('mod', client.is_mod)
            ]

    # Try and find the most elevated description
    command_info, found_match, command_authorization = None, False, False
    for (rank, authorized) in ranks_to_try:
        try:
            pre_info = client.server.commandhelp[rank][arg]
        except KeyError:
            continue

        found_match = True
        if not authorized: # Check if client is authorized to use this command with this rank
            break # If not authorized now, won't be authorized later, so break out

        command_info = pre_info
        command_authorization = True # This means at least one suitable variant of the command
        # that can be run with the user's rank was found

    # If a command was found somewhere among the user's available commands, command_info
    # would be non-empty.
    if not found_match:
        raise ClientError('Could not find help for command "{}"'.format(arg))

    message = 'Help for command "{}"'.format(arg)
    # If user was not authorized to run the command, display help for command version that requires
    # the least rank possible.
    if not command_authorization:
        command_info = pre_info

    for detail in command_info:
        message += ('\n' + detail)

    if not command_authorization:
        message += ('\nYou need rank at least {} to use this command.'.format(rank))

    client.send_ooc(message)

def ooc_cmd_iclock(client, arg):
    """ (STAFF ONLY)
    Toggles IC messages by non-staff in the current area being allowed/disallowed. Returns an error
    if not authorized, or if a GM attempts to lock IC in an area where such an action is forbidden.

    SYNTAX
    /iclock

    PARAMETERS
    None

    EXAMPLES
    /iclock
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')
    if not (client.is_mod or client.is_cm) and (client.is_gm and not client.area.gm_iclock_allowed):
        raise ClientError('GMs are not authorized to change IC locks in this area.')
    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    client.area.ic_lock = not client.area.ic_lock
    status = {True: 'locked', False: 'unlocked'}

    client.send_ooc('You {} the IC chat in this area.'.format(status[client.area.ic_lock]))
    client.send_ooc_others('A staff member has {} the IC chat in this area.'
                           .format(status[client.area.ic_lock]), is_staff=False, in_area=True)
    client.send_ooc_others('(X) {} has {} the IC chat in area {} ({}).'
                           .format(client.name, status[client.area.ic_lock], client.area.name,
                                   client.area.id), is_staff=True)

    logger.log_server('[{}][{}]Changed IC lock to {}'
                      .format(client.area.id, client.get_char_name(), client.area.ic_lock), client)

def ooc_cmd_invite(client, arg):
    """ (STAFF ONLY)
    Adds a client based on client ID or IPID to the area's invite list. If given IPID, it will
    invite all clients opened by the user. Otherwise, it will just do it to the given client.
    Returns an error if the given identifier does not correspond to a user.

    SYNTAX
    /invite <client_id>
    /invite <client_ipid>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)
    <client_ipid>: IPID for the client (number in parentheses in /getarea)

    EXAMPLES
    /invite 1                     :: Invites the player whose client ID is 1.
    /invite 1234567890            :: Invites all clients of the player whose IPID is 1234567890.
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')
    if not client.area.is_locked and not client.area.is_modlocked and not client.area.is_gmlocked:
        raise ClientError('Area is not locked.')

    # Invite matching targets
    for c in Constants.parse_id_or_ipid(client, arg):
        client.area.invite_list[c.ipid] = None
        client.send_ooc('Client {} has been invited to your area.'.format(c.id))
        c.send_ooc('You have been invited to area {}.'.format(client.area.name))

def ooc_cmd_judgelog(client, arg):
    """ (STAFF ONLY)
    List the last 20 judge actions performed in the current area. This includes using the judge
    buttons and changing the penalty bars. If given an argument, it will return the judgelog of the
    given area by ID or name. Otherwise, it will obtain the one from the current area.
    Returns an error if the given identifier does not correspond to an area.

    SYNTAX
    /judgelog {target_area}

    OPTIONAL PARAMETERS
    {target_area}: area whose judgelog will be returned (either ID or name)

    EXAMPLE
    If currently in the Basement (area 0)...
    /judgelog           :: You may get something like the next example
    /judgelog 0         :: You may get something like this

    == Judge log of Basement (0) ==
    *Sat Jun 29 12:06:03 2019 | [1] Judge (1234567890) used judge button testimony1.
    *Sat Jun 29 12:06:07 2019 | [1] Judge (1234567890) used judge button testimony4.
    *Sat Jun 29 12:06:12 2019 | [1] Judge (1234567890) changed penalty bar 2 to 9.
    *Sat Jun 29 12:06:12 2019 | [1] Judge (1234567890) changed penalty bar 2 to 8.
    *Sat Jun 29 12:06:14 2019 | [1] Judge (1234567890) changed penalty bar 1 to 9.
    *Sat Jun 29 12:06:15 2019 | [1] Judge (1234567890) changed penalty bar 1 to 8.
    *Sat Jun 29 12:06:16 2019 | [1] Judge (1234567890) changed penalty bar 1 to 7.
    *Sat Jun 29 12:06:17 2019 | [1] Judge (1234567890) changed penalty bar 1 to 8.
    *Sat Jun 29 12:06:19 2019 | [1] Judge (1234567890) changed penalty bar 2 to 9.
    """

    Constants.command_assert(client, arg, is_staff=True)
    if len(arg) == 0:
        arg = client.area.name

    # Obtain matching area's judgelog
    for area in Constants.parse_area_names(client, [arg]):
        info = area.get_judgelog()
        client.send_ooc(info)

def ooc_cmd_kick(client, arg):
    """ (CM AND MOD ONLY)
    Kicks a user from the server. The target is identified by either client ID (number in brackets)
    or IPID (number in parentheses). If given IPID, it will kick all clients opened by the user.
    Otherwise, it will just kick the given client.
    Returns an error if the given identifier does not correspond to a user.

    SYNTAX
    /kick <client_id>
    /kick <client_ipid>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)
    <client_ipid>: IPID for the client (number in parentheses in /getarea)

    EXAMPLES
    /kick 1                     :: Kicks client whose ID is 1.
    /kick 1234567890            :: Kick all clients opened by the user whose IPID is 1234567890.
    """

    if not client.is_mod and not client.is_cm:
        raise ClientError('You must be authorized to do that.')

    # Kick matching targets
    for c in Constants.parse_id_or_ipid(client, arg):
        client.send_ooc('You kicked {} [{}/{}].'.format(c.displayname, c.ipid, c.hdid))
        client.send_ooc_others('{} was kicked.'.format(c.displayname),
                               pred=lambda x: not (x.is_mod or x.is_cm), in_area=True)
        client.send_ooc_others('{} kicked {} [{}/{}].'
                               .format(client.name, c.displayname, c.ipid, c.hdid),
                               pred=lambda x: x.is_mod or x.is_cm)
        logger.log_server('Kicked {}.'.format(c.ipid), client)
        c.disconnect()

def ooc_cmd_kickself(client, arg):
    """
    Kicks other clients opened by the current user. Useful whenever a user loses connection and the
    old client is ghosting.

    SYNTAX
    /kickself

    PARAMETERS
    None

    EXAMPLES
    /kickself
    """

    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    for target in client.get_multiclients():
        if target != client:
            target.disconnect()

    client.send_ooc('Kicked other instances of client.')

def ooc_cmd_knock(client, arg):
    """
    'Knock' on some area's door, sending a notification to users in said area.
    Returns an error if the area could not be found, if the user is already in the target area,
    if the area cannot be reached as per the DEFAULT server configuration (as users may lock
    passages, but that does not mean the door no longer exists, usually), or if the user is either
    in an area marked as lobby or attempting to knock the door to a lobby area.

    SYNTAX
    /knock <area_name>
    /knock <area_id>

    PARAMETERS
    <area_name>: Name of the area whose door you want to knock.
    <area_id>: ID of the area whose door you want to knock.

    EXAMPLES
    /knock 0                :: Knock the door to area 0
    /knock Courtroom, 2     :: Knock the door to area "Courtroom, 2"
    """

    if len(arg) == 0:
        raise ArgumentError('This command takes one argument.')

    # Get area by either name or ID
    try:
        target_area = client.server.area_manager.get_area_by_name(arg)
    except AreaError:
        try:
            target_area = client.server.area_manager.get_area_by_id(int(arg))
        except Exception:
            raise ArgumentError('Could not parse area name {}.'.format(arg))

    # Filter out edge cases
    if target_area.name == client.area.name:
        raise ClientError('You cannot knock on the door of your current area.')
    if client.area.lobby_area:
        raise ClientError('You cannot knock doors from a lobby area.')
    if target_area.lobby_area:
        raise ClientError('You cannot knock the door to a lobby area.')

    if client.area.default_reachable_areas != {'<ALL>'} and \
    target_area.name not in client.area.default_reachable_areas | client.area.reachable_areas:
        raise ClientError('You tried to knock on the door to {} but you realized the room is too '
                          'far away.'.format(target_area.name))

    client.send_ooc('You knocked on the door to area {}.'.format(target_area.name))
    client.send_ooc_others('Someone knocked on your door from area {}.'.format(client.area.name),
                           is_staff=False, in_area=target_area, to_deaf=False)
    client.send_ooc_others('(X) {} knocked on the door to area {} in area {} ({}).'
                           .format(client.displayname, target_area.name, client.area.name,
                                   client.area.id), is_staff=True)

    for c in client.area.clients:
        c.send_ic(msg='', ding=0 if c.is_deaf else 7)
    for c in target_area.clients:
        c.send_ic(msg='', ding=0 if c.is_deaf else 7)

def ooc_cmd_lasterror(client, arg):
    """ (MOD ONLY)
    Obtain the latest uncaught error as a result of a client packet. This message emulates what is
    output on the server console (i.e. it includes the full traceback as opposed to just the last
    error which is what is usually sent to the offending client).
    Note that ClientErrors, ServerErrors, AreaErrors and Argumenterrors are usually caught by the
    client itself, and would not normally cause issues.
    Returns a (Client)error if no errors had been raised and not been caught since server bootup.

    SYNTAX
    /lasterror

    PARAMETERS
    None

    EXAMPLE
    /lasterror      :: May return something like this:

     The last uncaught error message was the following:
    TSUSERVER HAS ENCOUNTERED AN ERROR HANDLING A CLIENT PACKET
    *Server time: Mon Jul 1 14:10:26 2019
    *Packet details: CT ['Iuvee', '/lasterror']
    *Client status: C::0:1639795399:Iuvee:Kaede Akamatsu_HD:True:0
    *Area status: A::0:Basement:1
    Traceback (most recent call last):
    File "...\server\aoprotocol.py", line 88, in data_received
    self.net_cmd_dispatcher[cmd](self, args)
    File "...\server\aoprotocol.py", line 500, in net_cmd_ct
    function(self.client, arg)
    File "...\server\commands.py", line 4210, in ooc_cmd_lasterror
    final_trace = "".join(traceback.format_exc(etype, evalue, etraceback))
    TypeError: format_exc() takes from 0 to 2 positional arguments but 3 were given

    Note: yes, this is an error message that was created while testing this command.
    """

    if not client.is_mod:
        raise ClientError('You must be authorized to do that.')
    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')
    if not client.server.last_error:
        raise ClientError('No error messages have been raised and not been caught since server bootup.')

    pre_info, etype, evalue, etraceback = client.server.last_error
    final_trace = "".join(traceback.format_exception(etype, evalue, etraceback))
    info = ('The last uncaught error message was the following:\n{}\n{}'
            .format(pre_info, final_trace))
    client.send_ooc(info)

def ooc_cmd_lights(client, arg):
    """
    Toggles lights on or off in the background. If area is background locked, it requires mod
    privileges. If turned off, the background will change to the server's blackout background.
    If turned on, the background will revert to the background before the blackout one.

    SYNTAX
    /lights <new_status>

    PARAMETERS
    <new_status>: 'on' or 'off'

    EXAMPLES
    Assuming lights were initially turned on
    /lights off             :: Turns off lights
    /lights on              :: Turns on lights
    """

    if len(arg) == 0:
        raise ArgumentError('You must specify either on or off.')
    if arg not in ['off', 'on']:
        raise ClientError('Expected on or off.')
    if not client.is_staff() and not client.area.has_lights:
        raise AreaError('This area has no lights to turn off or on.')
    if not client.is_mod and client.area.bg_lock:
        raise AreaError('The background of this area is locked.')

    if not client.is_staff() and client.is_blind:
        new_lights = not client.area.lights
    else:
        new_lights = (arg == 'on')
    client.area.change_lights(new_lights, initiator=client)

def ooc_cmd_lm(client, arg):
    """ (MOD ONLY)
    Similar to /lm, but only broadcasts the message to users in the current area, regardless of
    their global chat status.
    Returns an error if the user sends an empty message.

    SYNTAX
    /lm <message>

    PARAMETERS
    <message>: Message to be sent

    EXAMPLE
    /lm Hello World     :: Sends Hello World to all users in the current area, preceded with [MOD].
    """

    try:
        Constants.command_assert(client, arg, is_mod=True, parameters='>0')
    except ArgumentError:
        raise ArgumentError('You cannot send an empty message.')

    client.area.send_command('CT', '{}[MOD][{}]'
                             .format(client.server.config['hostname'], client.displayname), arg)
    logger.log_server('[{}][{}][LOCAL-MOD]{}.'
                      .format(client.area.id, client.get_char_name(), arg), client)

def ooc_cmd_lock(client, arg):
    """
    Locks the current area, preventing anyone not in the area (except staff) from joining. It also
    clears out the current invite list.
    Returns an error if the area does not allow locking or is already locked.

    SYNTAX
    /lock

    PARAMETERS
    None

    EXAMPLE
    /lock
    """

    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    if not client.area.locking_allowed:
        raise ClientError('Area locking is disabled in this area.')
    if client.area.is_locked:
        raise ClientError('Area is already locked.')

    client.area.is_locked = True
    for i in client.area.clients:
        client.area.invite_list[i.ipid] = None

    client.area.broadcast_ooc('Area locked.')

def ooc_cmd_login(client, arg):
    """
    Logs in current user as a moderator, provided they input the correct password.

    SYNTAX
    /login <mod_password>

    PARAMETERS
    <mod_password>: Mod password, found in \config\config.yaml

    EXAMPLES
    /login Mod      :: Attempt to log in as mod with "Mod" as password.
    """

    client.login(arg, client.auth_mod, 'moderator')

def ooc_cmd_logincm(client, arg):
    """
    Logs in current user as a community manager, provided they input the correct password.

    SYNTAX
    /logincm <cm_password>

    PARAMETERS
    <cm_password>: Community manager password, found in \config\config.yaml

    EXAMPLES
    /logincm CM     :: Attempt to log in as community maanger with "CM" as password.
    """

    client.login(arg, client.auth_cm, 'community manager')

def ooc_cmd_loginrp(client, arg):
    """
    Logs in current user as a game master, provided they input the correct password.

    SYNTAX
    /loginrp <gm_password>

    PARAMETERS
    <gm_password>: Game master password, found in \config\config.yaml

    EXAMPLES
    /loginrp GM     :: Attempt to log in as game master with "GM" as password.
    """

    client.login(arg, client.auth_gm, 'game master')

def ooc_cmd_logout(client, arg):
    """
    Logs out the current user from all staff roles and puts them in RP mode if needed.

    SYNTAX
    /logout

    PARAMETERS
    None

    EXAMPLE
    /logout
    """

    Constants.command_assert(client, arg, parameters='=0')

    client.is_mod = False
    client.is_gm = False
    client.is_cm = False
    client.send_ooc('You are no longer logged in.')

    # Clean-up operations
    if client.server.rp_mode:
        client.in_rp = True
    if client.area.evidence_mod == 'HiddenCM':
        client.area.broadcast_evidence_list()

    # Update the music list to show reachable areas and activate the AFK timer
    client.reload_music_list()
    client.server.create_task(client, ['as_afk_kick', client.area.afk_delay, client.area.afk_sendto])

    # If using a character restricted in the area, switch out
    if client.get_char_name() in client.area.restricted_chars:
        try:
            new_char_id = client.area.get_rand_avail_char_id(allow_restricted=False)
        except AreaError:
            new_char_id = -1 # Force into spectator mode if all other available characters are taken
        client.change_character(new_char_id)
        client.send_ooc('Your character has been set to restricted in this area by a staff member. '
                        'Switching you to {}.'.format(client.get_char_name()))

def ooc_cmd_look(client, arg):
    """
    Obtain the current area's description, which is either the description in the area list
    configuration, or a customized one defined via /look_set. If the area has no set description,
    it will return the server's default description stored in the default_area_description server
    parameter. If the area has its lights turned off, it will send a generic 'cannot see anything'
    message to non-staff members.

    SYNTAX
    /look

    PARAMETERS
    None

    EXAMPLES
    If the current area's description is "Literally a courtroom"...
    /look               :: Returns "Literally a courtroom"
    """

    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')
    if not client.is_staff() and client.is_blind:
        raise ClientError('You are blind, so you cannot see anything.')
    if not client.is_staff() and not client.area.lights:
        raise ClientError('The lights are off, so you cannot see anything.')

    client.send_ooc(client.area.description)

def ooc_cmd_look_clean(client, arg):
    """ (STAFF ONLY)
    Restores the default area descriptions of the given areas by ID or name separated by commas.
    If not given any areas, it will restore the default area description of the current area.

    SYNTAX
    /look_clean {area_1}, {area_2}, ....

    OPTIONAL PARAMETERS
    {area_n}: Area ID or name

    EXAMPLE
    Assuming the player is in area 0
    /look_clean                           :: Restores the default area description in area 0
    /look_clean 3, Class Trial Room,\ 2   :: Restores the default area descriptions in area 3 and Class Trial Room, 2 (note the ,\)
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')

    if len(arg) == 0:
        areas_to_clean = [client.area]
    else:
        # Make sure the input is valid before starting
        raw_areas_to_clean = arg.split(", ")
        areas_to_clean = set(Constants.parse_area_names(client, raw_areas_to_clean))

    successful_cleans = set()
    for area in areas_to_clean:
        area.description = area.default_description
        client.send_ooc_others('The area description was updated to {}.'.format(area.description),
                               is_staff=False, in_area=area)
        successful_cleans.add(area.name)

    if len(successful_cleans) == 1:
        message = str(successful_cleans.pop())
        client.send_ooc('Restored the original area description of area {}.'
                        .format(message))
        client.send_ooc_others('(X) {} restored the original area description of area {}.'
                               .format(client.name, message), is_staff=True)
    elif len(successful_cleans) > 1:
        message = Constants.cjoin(successful_cleans)
        client.send_ooc('Restored the original area descriptions of areas {}.'
                        .format(message))
        client.send_ooc_others('(X) {} restored the original area descriptions of areas {}.'
                               .format(client.name, message), is_staff=True)

    logger.log_server('[{}][{}]Reset the area description in {}.'
                      .format(client.area.id, client.get_char_name(), message), client)

def ooc_cmd_look_list(client, arg):
    """ (STAFF ONLY)
    Lists all areas that contain custom descriptions.

    SYNTAX
    /look_list

    PARAMETERS
    None

    EXAMPLE
    If area 0 called Basement is the only one with a custom description, and its description
    happens to be "Not a courtroom"...
    /look_list              :: May return something like
    == Areas in this server with custom descriptions ==
    *(0) Basement: Not a courtroom
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')
    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    info = '== Areas in this server with custom descriptions =='
    # Get all areas with changed descriptions
    areas = [area for area in client.server.area_manager.areas if area.description != area.default_description]

    # No areas found means there are no areas with changed descriptions
    if len(areas) == 0:
        info += '\r\n*No areas have changed their description.'
    # Otherwise, build the list of all areas with changed descriptions
    else:
        for area in areas:
            info += '\r\n*({}) {}: {}'.format(area.id, area.name, area.description)

    client.send_ooc(info)

def ooc_cmd_look_set(client, arg):
    """ (STAFF ONLY)
    Sets (and replaces!) the area description of the current area to the given one.
    If not given any description, it will set the description to be the area's default description.
    Requires /look_clean to undo.

    SYNTAX
    /look_set {area_description}

    OPTIONAL PARAMETERS
    {area_description}: New area description

    EXAMPLE
    Assuming the player is in area 0, which was set to have a default description of "A courtroom"
    /look_set "Not literally a courtroom"       :: Sets the area description in area 0 to be "Not literally a courtroom".
    /look_set                                   :: Sets the area description in area 0 to be the default "A courtroom".
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')

    if len(arg) == 0:
        client.area.description = client.area.default_description
        client.send_ooc('Reset the area description to its original value.')
        client.send_ooc_others('(X) {} reset the area description of area {} to its original value.'
                               .format(client.name, client.area.name), is_staff=True)
        logger.log_server('[{}][{}]Reset the area description in {}.'
                          .format(client.area.id, client.get_char_name(), client.area.name), client)

    else:
        client.area.description = arg
        client.send_ooc('Updated the area descriptions to {}'.format(arg))
        client.send_ooc_others('(X) {} set the area descriptions of area {} to {}.'
                               .format(client.name, client.area.name, client.area.description),
                               is_staff=True)
        logger.log_server('[{}][{}]Set the area descriptions to {}.'
                          .format(client.area.id, client.get_char_name(), arg), client)

    client.send_ooc_others('The area description was updated to {}.'
                           .format(client.area.description), is_staff=False, in_area=True)

def ooc_cmd_minimap(client, arg):
    """
    Lists all areas that can be reached from the current area according to areas.yaml and passages
    set in-game.
    Returns all areas if no passages were defined or created for the current area.

    SYNTAX
    /minimap

    PARAMETERS
    None

    EXAMPLE
    /minimap
    """

    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    info = '== Areas reachable from {} =='.format(client.area.name)
    try:
        # Get all reachable areas and sort them by area ID
        sorted_areas = sorted(client.area.reachable_areas,
                              key=lambda area_name: client.server.area_manager.get_area_by_name(area_name).id)

        # No areas found or just the current area found means there are no reachable areas.
        if len(sorted_areas) == 0 or sorted_areas == [client.area.name]:
            info += '\r\n*No areas available.'
        # Otherwise, build the list of all reachable areas
        else:
            for area in sorted_areas:
                if area != client.area.name:
                    info += '\r\n*{}-{}'.format(client.server.area_manager.get_area_by_name(area).id, area)
    except AreaError:
        # In case no passages are set, send '<ALL>' as default answer.
        info += '\r\n<ALL>'

    client.send_ooc(info)

def ooc_cmd_modlock(client, arg):
    """ (MOD ONLY)
    Sets the current area as accessible only to moderators. Players in the area at the time of the
    lock will be able to leave and return to the area, regardless of authorization.
    Requires /unlock to undo.

    Returns an error if the area is already mod-locked or if the area is set to be unlockable.

    SYNTAX
    /modlock

    PARAMETERS
    None

    EXAMPLE
    /modlock             :: Sets the current area as accessible only to staff members.
    """

    if not client.is_mod:
        raise ClientError('You must be authorized to do that.')
    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    if not client.area.locking_allowed:
        raise ClientError('Area locking is disabled in this area')
    if client.area.is_modlocked:
        raise ClientError('Area is already mod-locked.')

    client.area.is_modlocked = True
    client.area.broadcast_ooc('Area mod-locked.')
    for i in client.area.clients:
        client.area.invite_list[i.ipid] = None

def ooc_cmd_motd(client, arg):
    """
    Returns the server's Message Of The Day.

    SYNTAX
    /motd

    PARAMETERS
    None

    EXAMPLES
    /motd
    """

    Constants.command_assert(client, arg, parameters='=0')

    client.send_motd()

def ooc_cmd_multiclients(client, arg):
    """ (STAFF ONLY)
    Lists all clients and the areas they are opened by a player by client ID or IPID.
    Returns an error if the given identifier does not correspond to a user.

    SYNTAX
    /multiclients <client_id>
    /multiclients <client_ipid>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)
    <client_ipid>: IPID for the client (number in parentheses in /getarea)

    EXAMPLES
    Assuming client 1 with IPID 1234567890 is in the Basement (area 0) and has another client open,
    whose client ID is 4...
    /multiclients 1             :: May return something like the example below:
    /multiclients 1234567890    :: May return something like the following:

    == Clients of 1234567890 ==
    == Area 0: Basement ==
    [1] Spam_HD (1234567890)
    == Area 4: Test 1 ==
    [4] Eggs_HD (1234567890)
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')

    target = Constants.parse_id_or_ipid(client, arg)[0]
    info = target.prepare_area_info(client.area, -1, False, as_mod=client.is_staff(),
                                    only_my_multiclients=True)
    info = '== Clients of {} =={}'.format(target.ipid, info)
    client.send_ooc(info)

def ooc_cmd_music_list(client, arg):
    """
    Sets the client's current music list. This list is persistent between area changes and works on
    a client basis. If given no arguments, it will return the music list to its default value
    (in music.yaml). The list of music lists can be accessed with /music_lists. Clients that do not
    process 'SM' packets can use this command without crashing, but it will have no visual effect.
    Returns an error if the given music list was not found.

    SYNTAX
    /music_list <music_list>

    PARAMETERS
    <music_list>: Name of the intended music_list

    EXAMPLES
    /music_list dr2         :: Load the "dr2" music list.
    /music_list             :: Reset the music list to its default value.
    """

    if len(arg) == 0:
        client.music_list = None
        client.reload_music_list()
        client.send_ooc('Restored music list to its default value.')
    else:
        try:
            new_music_file = 'config/music_lists/{}.yaml'.format(arg)
            client.reload_music_list(new_music_file=new_music_file)
        except ServerError:
            raise ArgumentError('Could not find music list file: {}'.format(arg))

        client.send_ooc('Loaded music list: {}'.format(arg))

def ooc_cmd_music_lists(client, arg):
    """
    Lists all available music lists as established in config/music_lists.yaml
    Note that, as this file is updated independently from the other music lists,
    some music list does not need to be in this file in order to be usable, and
    a music list in this list may no longer exist.

    SYNTAX
    /music_lists

    PARAMETERS
    None

    EXAMPLES
    /music_lists            :: Return all available music lists
    """

    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    try:
        with Constants.fopen('config/music_lists.yaml', 'r') as f:
            output = 'Available music lists:\n'
            for line in f:
                output += '*{}'.format(line)
            client.send_ooc(output)
    except ServerError as exc:
        if exc.code == 'FileNotFound':
            raise ClientError('Server file music_lists.yaml not found.')
        raise # Weird exception, reraise

def ooc_cmd_mute(client, arg):
    """ (CM AND MOD ONLY)
    Mutes given user based on client ID or IPID so that they are unable to speak in IC chat.
    If given IPID, it will mute all clients opened by the user. Otherwise, it will just mute the
    given client.
    Requires /unmute to undo.
    Returns an error if the given identifier does not correspond to a user.

    SYNTAX
    /mute <client_id>
    /mute <client_ipid>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)
    <client_ipid>: IPID for the client (number in parentheses in /getarea)

    EXAMPLES
    /mute 1                     :: Mutes client whose ID is 1.
    /mute 1234567890            :: Mutes all clients opened by the user whose IPID is 1234567890.
    """

    if not client.is_mod and not client.is_cm:
        raise ClientError('You must be authorized to do that.')

    # Mute matching targets
    for c in Constants.parse_id_or_ipid(client, arg):
        logger.log_server('Muted {}.'.format(c.ipid), client)
        client.area.broadcast_ooc("{} was muted.".format(c.get_char_name()))
        c.is_muted = True

def ooc_cmd_online(client, arg):
    """
    Returns how many players are online.

    SYNTAX
    /online

    PARAMETERS
    None

    EXAMPLE
    If there are 2 players online in a server of maximum capacity 100
    /online         :: Will return: "Online: 2/100"
    """

    Constants.command_assert(client, arg, parameters='=0')

    client.send_ooc("Online: {}/{}"
                    .format(client.server.get_player_count(), client.server.config['playerlimit']))

def ooc_cmd_ooc_mute(client, arg):
    """ (MOD AND CM ONLY)
    Mutes a player from the OOC chat by their OOC username.
    Requires /ooc_unmute to undo.
    Returns an error if no player has the given OOC username.

    SYNTAX
    /ooc_mute <ooc_name>

    PARAMETERS
    <ooc_name>: Client OOC username

    EXAMPLE
    /ooc_mute Aba           :: Mutes from OOC the player whose username is Aba
    """

    if not client.is_mod and not client.is_cm:
        raise ClientError('You must be authorized to do that.')
    if len(arg) == 0:
        raise ArgumentError('You must specify a target. Use /ooc_mute <ooc_name>.')

    targets = client.server.client_manager.get_targets(client, TargetType.OOC_NAME, arg, False)
    if not targets:
        raise ArgumentError('Targets not found. Use /ooc_mute <ooc_name>.')

    for c in targets:
        c.is_ooc_muted = True
        logger.log_server('OOC-muted {}.'.format(c.ipid), client)
        client.area.broadcast_ooc("{} was OOC-muted.".format(c.name))

def ooc_cmd_ooc_unmute(client, arg):
    """ (MOD AND CM ONLY)
    Unmutes a player from the OOC chat by their OOC username.
    Requires /ooc_mute to undo.
    Returns an error if no player has the given OOC username.

    SYNTAX
    /ooc_unmute <ooc_name>

    PARAMETERS
    <ooc_name>: Client OOC username

    EXAMPLE
    /ooc_unmute Aba         :: Unmutes from OOC the player whose username is Aba
    """

    if not client.is_mod and not client.is_cm:
        raise ClientError('You must be authorized to do that.')
    if len(arg) == 0:
        raise ArgumentError('You must specify a target. Use /ooc_mute <ooc_name>.')

    targets = client.server.client_manager.get_targets(client, TargetType.OOC_NAME, arg, False)
    if not targets:
        raise ArgumentError('Target not found. Use /ooc_mute <ooc_name>.')

    for c in targets:
        c.is_ooc_muted = False
        logger.log_server('OOC-unmuted {}.'.format(c.ipid), client)
        client.area.broadcast_ooc("{} was OOC-unmuted.".format(c.name))

def ooc_cmd_party(client, arg):
    """
    Creates a party and makes you the leader of it. Party members will all move in groups
    automatically. It also returns a party ID players can use to join the party.
    Returns an error if the player is in area where the lights are off, if the server has
    reached its party limit, or if they are following someone.

    SYNTAX
    /party

    PARAMETERS
    None

    EXAMPLES
    /party      :: May return something like "You have created party 11037."
    """

    Constants.command_assert(client, arg, parameters='=0')

    if not client.is_staff() and client.is_blind:
        raise ClientError('You cannot create a party as you are blind.')
    if not client.area.lights:
        raise AreaError('You cannot create a party while the lights are off.')
    if client.following:
        raise PartyError('You cannot create a party while following someone.')

    party = client.server.party_manager.new_party(client, tc=True)
    client.send_ooc('You have created party {}.'.format(party.get_id()))
    client.send_ooc_others('(X) {} has created party {} ({}).'
                           .format(client.displayname, party.get_id(), client.area.id),
                           is_staff=True)

def ooc_cmd_party_disband(client, arg):
    """ (VARYING REQUIREMENTS)
    Disbands your party if not given arguments, or (STAFF ONLY) disbands a party by party ID.
    Also sends notifications to the former members if you were visible.
    Returns an error for non-authorized users if they try to disband other parties or they are not
    a leader of their own party.

    SYNTAX
    /party_disband {party_id}

    OPTIONAL PARAMETERS
    {party_id}: Party to disband

    EXAMPLES
    If you were part of party 11037...
    /party_disband          :: Disbands party 11037
    /party_disband 11037    :: Disbands party 11037
    /party_disband 73011    :: Disbands party 73011
    """

    if client.is_staff():
        Constants.command_assert(client, arg, parameters='<2')
    else:
        Constants.command_assert(client, arg, parameters='=0')

    if not arg:
        party = client.get_party()
    else:
        party = client.server.party_manager.get_party(arg)

    if not party.is_leader(client) and not client.is_staff():
        raise PartyError('You are not a leader of your party.')

    client.server.party_manager.disband_party(party)
    if arg:
        client.send_ooc('You have disbanded party {}.'.format(party.get_id()))
    else:
        client.send_ooc('You have disbanded your party.')

    culprit = client.displayname if not arg else 'A staff member'
    for x in party.get_members(uninclude={client}):
        if x.is_staff() or client.is_visible:
            x.send_ooc('{} has disbanded your party.'.format(culprit))

def ooc_cmd_party_id(client, arg):
    """
    Obtains your party ID.
    Returns an error if you are not part of a party.

    SYNTAX
    /party_id

    PARAMETERS
    None

    EXAMPLES
    If you were part of party 11037...
    /party_id           :: May return something like "Your party ID is 11037".
    """

    Constants.command_assert(client, arg, parameters='=0')

    party = client.get_party(tc=True)
    client.send_ooc('Your party ID is: {}'.format(party.get_id()))

def ooc_cmd_party_invite(client, arg):
    """
    Sends an invite to another player by client ID to join the party. The invitee will receive an
    OOC message with your name and party ID so they can join.
    The invitee must be in the same area as the player. If that is not the case, but the invitee
    is in an area that can be reached by screams and is not deaf, they will receive a notification
    of the party invitation attempt (but will not be invited).
    Returns an error if you are not part of a party, you are not a party leader or staff member,
    if the player is not in the same area as you, or if the player is already invited.

    SYNTAX
    /party_invite <client_id>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)

    EXAMPLES
    /party_invite 2         :: Invites the player with ID 2 to join your party.
    """

    Constants.command_assert(client, arg, parameters='=1')

    party = client.get_party(tc=True)
    if not party.is_leader(client) and not client.is_staff():
        raise PartyError('You are not a leader of your party.')

    c = Constants.parse_id(client, arg)
    # Check if invitee is in the same area
    if c.area != party.area:
        if c.area.name in client.area.scream_range and not c.is_deaf:
            msg = ('You hear screeching of someone asking you to join their party but they seem '
                   'too far away to even care all that much.')
            c.send_ooc(msg)
        raise PartyError('The player is not in your area.')

    party.add_invite(c, tc=False)

    client.send_ooc('You have invited {} to join your party.'.format(c.displayname))
    for x in party.get_leaders(uninclude={client}):
        x.send_ooc('{} has invited {} to join your party.'
                   .format(client.displayname, c.displayname))
    c.send_ooc('{} has invited you to join their party {}.'
               .format(client.displayname, party.get_id()))

def ooc_cmd_party_join(client, arg):
    """
    Enrolls you into a party by party ID provided you were previously invited to it.
    Returns an error if you are already part of a party, if the party reached its maximum number
    of members, or if you are following someone.

    SYNTAX
    /party_join <party_id>

    PARAMETERS
    <party_id>: Party ID

    EXAMPLES
    /party_join 11037       :: If previously invited, you will join party 11037.
    """

    Constants.command_assert(client, arg, split_spaces=True, parameters='=1')
    if client.following:
        raise PartyError('You cannot join a party while following someone.')

    party = client.server.party_manager.get_party(arg)
    party.add_member(client, tc=True)

    client.send_ooc('You have joined party {}.'.format(party.get_id()))

    for c in party.get_members(uninclude={client}):
        if c.is_staff() or client.is_visible:
            c.send_ooc('{} has joined your party.'.format(client.displayname))

def ooc_cmd_party_kick(client, arg):
    """
    Kicks a player by client ID off your party. Also sends a notification to party leaders and the
    target if you were visible.
    Returns an error if you are not a leader of your party or the target is not a member.

    SYNTAX
    /party_kick <client_id>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)

    EXAMPLES
    /party_kick 2       :: Kicks the player with client ID 2 off your party.
    """

    Constants.command_assert(client, arg, parameters='=1')

    party = client.get_party()
    if not party.is_leader(client) and not client.is_staff():
        raise PartyError('You are not a leader of your party.')

    c = Constants.parse_id(client, arg)
    if c == client:
        raise PartyError('You cannot kick yourself off your party.')

    party.remove_member(c)
    client.send_ooc('You have kicked {} off your party.'.format(c.displayname))
    if c.is_staff() or client.is_visible:
        c.send_ooc('{} has kicked you off your party.'.format(client.displayname))
    for x in party.get_leaders(uninclude={client}):
        if x.is_staff() or client.is_visible:
            x.send_ooc('{} has kicked {} off your party.'
                       .format(client.displayname, c.displayname))

def ooc_cmd_party_lead(client, arg):
    """
    Sets you as leader of your party and announces all other party leaders of it. Party leaders
    can send invites to other players to join the party.
    Returns an error if you are not part of a party or you are already a leader.

    SYNTAX
    /party_lead

    PARAMETERS
    None

    EXAMPLES
    /party_lead         :: Sets you as leader of your party.
    """

    Constants.command_assert(client, arg, parameters='=0')

    party = client.get_party()
    party.add_leader(client, tc=True)
    client.send_ooc('You are now a leader of your party.')
    for c in party.get_leaders(uninclude={client}):
        if c.is_staff() or client.is_visible:
            c.send_ooc('{} is now a leader of your party.'.format(client.displayname))

def ooc_cmd_party_leave(client, arg):
    """
    Makes you leave your current party. It will also notify all other remaining members if you were
    not sneaking. If instead you were the only member of the party, the party will be disbanded.
    Returns an error if you are not part of a party.

    SYNTAX
    /party_leave

    PARAMETERS
    None

    EXAMPLES
    /party_leave        :: Makes you leave your current party.
    """

    Constants.command_assert(client, arg, parameters='=0')

    party = client.get_party(tc=True)
    party.remove_member(client)

    client.send_ooc('You have left party {}.'.format(party.get_id()))

    for c in party.get_members(uninclude={client}):
        if c.is_staff() or client.is_visible:
            c.send_ooc('{} has left your party.'.format(client.displayname))

def ooc_cmd_party_list(client, arg):
    """ (STAFF ONLY)
    Lists all active parties in the server. Includes details such as: party ID, the number of
    members it has and its member limit, the area the party is at, and who are its leaders and
    regular members.
    Returns an error if there are no active parties.

    SYNTAX
    /party_list

    PARAMETERS
    None

    EXAMPLES
    /party_list         :: May return something like this:
    == Active parties ==
    *Party 11037 [2/7] (3). Leaders: Phantom_HD. Regular members: Spam_HD
    """

    Constants.command_assert(client, arg, parameters='=0', is_staff=True)

    info = '== Active parties =='
    for party in client.server.party_manager.get_parties():
        pid, area, player_limit, raw_leaders, raw_regulars = party.get_details()
        num_members = len(raw_leaders.union(raw_regulars))
        leaders = ', '.join([c.displayname for c in raw_leaders]) if raw_leaders else 'None'
        regulars = ', '.join([c.displayname for c in raw_regulars]) if raw_regulars else 'None'
        info += ('\r\n*Party {} [{}/{}] ({}). Leaders: {}. Regular members: {}.'
                 .format(pid, num_members, player_limit, area.id, leaders, regulars))
    client.send_ooc(info)

def ooc_cmd_party_members(client, arg):
    """
    Obtains the leaders and regular members of your party. Any members that are sneaking will
    continue to appear in this list.
    Returns an error if you are not part of a party.

    SYNTAX
    /party_members

    PARAMETERS
    None

    EXAMPLES
    /party_members      :: May return something like this
    == Members of party 11037 ==
    *Leaders: Phantom_HD, Spam_HD
    *Members: Eggs_HD
    """

    Constants.command_assert(client, arg, parameters='=0')

    party = client.get_party(tc=True)
    regulars, leaders = party.get_members_leaders()

    info = '== Members of party {} =='.format(party.get_id())
    if leaders:
        info += '\r\n*Leaders: {}'.format(' '.join([str(c.displayname) for c in leaders]))
    if regulars:
        info += '\r\n*Members: {}'.format(' '.join([str(c.displayname) for c in regulars]))
    client.send_ooc(info)

def ooc_cmd_party_uninvite(client, arg):
    """
    Revokes an invitation for a player by client ID to join your party. They will no longer be able
    to join your party until they are invited again.
    Returns an error if you are not part of a party, you are not a party leader or staff member,
    or if the player is not invited.

    SYNTAX
    /party_uninvite <client_id>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)

    EXAMPLES
    /party_uninvite 2       :: Revokes the invitation sent to player with ID 2 to join your party.
    """

    Constants.command_assert(client, arg, split_spaces=True, parameters='=1')

    party = client.get_party(tc=True)
    if not party.is_leader(client) and not client.is_staff():
        raise PartyError('You are not a leader of your party.')

    c = Constants.parse_id(client, arg)
    party.remove_invite(c, tc=False)

    client.send_ooc('You have uninvited {} to join your party.'.format(c.displayname))
    for x in party.get_leaders(uninclude={client}):
        x.send_ooc('{} has uninvited {} to join your party.'
                   .format(client.displayname, c.displayname))
    c.send_ooc('{} has revoked your invitation to join their party {}.'
               .format(client.displayname, party.get_id()))

def ooc_cmd_party_unlead(client, arg):
    """
    Removes your party leader role and announces all other party leaders of it. If a party has no
    leaders, all leader functions are available to all members.
    Returns an error if you are not part of a party or you are not a leader.

    SYNTAX
    /party_unlead

    PARAMETERS
    None

    EXAMPLES
    /party_unlead       :: Removes your party leader role.
    """

    Constants.command_assert(client, arg, parameters='=0')

    party = client.get_party()
    party.remove_leader(client, tc=True)
    client.send_ooc('You are no longer a leader of your party.')
    for x in party.get_leaders(uninclude={client}):
        if x.is_staff() or client.is_visible:
            x.send_ooc('{} is no longer a leader of your party.'.format(client.displayname))

def ooc_cmd_passage_clear(client, arg):
    """ (STAFF ONLY)
    Clears all the passage locks that start in the areas between two given ones by name or ID, or
    does that only to the given area if not given any. In particular, players in any of the affected
    areas will be able to freely move to any other from the area they were in.
    Note that, as passages are unidirectional, passages from areas outside the given range that end
    in an area that is in the range will be conserved.

    SYNTAX
    /passage_clear
    /passage_clear <area_range_start>, <area_range_end>

    /passage_restore <area_range_start>, <area_range_end>

    PARAMETERS
    <area_range_start>: Start of area range (inclusive)
    <area_range_end>: End of area range (inclusive)

    EXAMPLES
    Assuming the player is in area 0...
    /passage_clear                :: Clears the passages starting in area 0.
    /passage_clear 16, 116        :: Restores the passages starting in areas 16 through 116.
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')
    areas = arg.split(', ')
    if len(areas) > 2:
        raise ClientError('This command takes at most two arguments.')

    areas = Constants.parse_two_area_names(client, areas)

    for i in range(areas[0].id, areas[1].id+1):
        area = client.server.area_manager.get_area_by_id(i)
        area.reachable_areas = {'<ALL>'}

    if areas[0] == areas[1]:
        client.send_ooc('Area passage locks have been removed in {}.'.format(areas[0].name))
    else:
        client.send_ooc('Area passage locks have been removed in areas {} through {}'
                        .format(areas[0].name, areas[1].name))

def ooc_cmd_passage_restore(client, arg):
    """ (STAFF ONLY)
    Restores the passages in the areas between two given ones by name or ID to their original state
    when the areas were loaded, or does that to the current area if not given any.
    Note that, as passages are unidirectional, passages from areas outside the given range that end
    in an area that is in the range will be conserved.

    SYNTAX
    /passage_restore
    /passage_restore <area_range_start>, <area_range_end>

    PARAMETERS
    <area_range_start>: Start of area range (inclusive)
    <area_range_end>: End of area range (inclusive)

    EXAMPLES
    Assuming the player is in area 0...
    /passage_restore                :: Restores the passages starting in area 0 to default.
    /passage_restore 16, 116        :: Restores the passages starting in areas 16 through 116.
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')
    areas = arg.split(', ')
    if len(areas) > 2:
        raise ClientError('This command takes at most two arguments.')

    areas = Constants.parse_two_area_names(client, areas)

    for i in range(areas[0].id, areas[1].id+1):
        area = client.server.area_manager.get_area_by_id(i)
        area.reachable_areas = set(list(area.default_reachable_areas)[:])
        area.change_reachability_allowed = area.default_change_reachability_allowed

    if areas[0] == areas[1]:
        client.send_ooc('Passages in this area have been restored to their original statue.')
    else:
        client.send_ooc('Passages in areas {} through {} have been restored to their original '
                        'state.'.format(areas[0].name, areas[1].name))

def ooc_cmd_ping(client, arg):
    """
    Returns "Pong" and nothing else. Useful to check if the player has lost connection.

    SYNTAX
    /ping

    PARAMETERS

    EXAMPLES
    /ping               :: Returns "Pong"
    """

    Constants.command_assert(client, arg, parameters='=0')

    client.send_ooc('Pong.')

def ooc_cmd_play(client, arg):
    """ (STAFF ONLY)
    Plays a given track, even if not explicitly in the music list. It is the way to play custom
    music. If the area parameter 'song_switch_allowed' is set to true, anyone in the area can use
    this command even if they are not logged in.

    SYNTAX
    /play <track_name>

    PARAMETERS:
    <track_name>: Track to play

    EXAMPLES:
    /play Trial(AJ).mp3         :: Plays Trial(AJ).mp3
    /play CustomTrack.mp3       :: Plays CustomTrack.mp3 (will only be audible to users with CustomTrack.mp3)
    """

    if not (client.is_staff() or client.area.song_switch_allowed):
        raise ClientError('You must be authorized to do that.')
    if len(arg) == 0:
        raise ArgumentError('You must specify a song.')

    client.area.play_music(arg, client.char_id, -1)
    client.area.add_music_playing(client, arg)
    logger.log_server('[{}][{}]Changed music to {}.'.format(client.area.id, client.get_char_name(), arg), client)

def ooc_cmd_pm(client, arg):
    """
    Sends a personal message to a specified user.
    Returns an error if the user could not be found, or if the user or target muted PMs.

    SYNTAX
    /pm <user_id> <message>

    PARAMETERS
    <user_id>: Either the character name, the OOC username, the custom showname or client ID (number in brackets in /getarea) of the intended recipient.
    <message>: Message to be sent.

    EXAMPLES
    /pm Santa What will I get for Christmas?    :: Sends that message to the user whose OOC name is Santa.
    /pm 0 Nothing                               :: Sends that message to the user whose client ID is 0.
    /pm Santa_HD Sad                            :: Sends that message to the user whose character name is Santa_HD.
    """

    if client.pm_mute:
        raise ClientError('You have muted all PM conversations.')
    args = arg.split()
    if len(args) < 2:
        raise ArgumentError('Not enough arguments. Use /pm <target> <message>. Target should be '
                            'char-name, custom showname, ID or OOC-name or char-name.')

    cm = client.server.client_manager

    # Pretend the identifier is a character name
    targets = cm.get_targets(client, TargetType.CHAR_NAME, arg, True)
    if targets:
        target_length = len(targets[0].get_char_name().split(' '))

    # If still needed, pretend the identifier is a custom showname
    if not targets:
        targets = cm.get_targets(client, TargetType.SHOWNAME, arg, True)
        if targets:
            target_length = len(targets[0].showname.split(' '))

    # If still needed, pretend the identifier is a client ID
    if not targets and args[0].isdigit():
        targets = cm.get_targets(client, TargetType.ID, int(args[0]), False)
        if targets:
            target_length = 1

    # If still needed, pretend the identifier is an OOC username
    if not targets:
        targets = cm.get_targets(client, TargetType.OOC_NAME, arg, True)
        if targets:
            target_length = len(targets[0].name.split(' '))

    # If no matching targets found, be sad.
    if not targets:
        raise ArgumentError('No targets found.')

    # Obtain the message from the given arguments
    msg = ' '.join(args[target_length:])
    recipient = ' '.join(args[:target_length])

    # Attempt to send the message to the target, provided they do not have PMs disabled.
    c = targets[0]
    if c.pm_mute:
        raise ClientError('This user muted all PM conversations.')

    client.send_ooc('PM sent to {}. Message: {}'.format(recipient, msg))
    c.send_ooc('PM from {} in {} ({}): {}'
               .format(client.name, client.area.name, client.displayname, msg))

def ooc_cmd_pos(client, arg):
    """
    Switches the character to the given position, or to its original position if not given one.
    Returns an error if position is invalid.

    SYNTAX
    /pos {new_position}

    OPTIONAL PARAMETERS
    {new_position}: New character position (jud, def, pro, hlp, hld)

    EXAMPLES
    /pos jud                :: Switches to the judge position
    /pos                    :: Resets to original position
    """

    # Resetting to original position
    if len(arg) == 0:
        client.change_position()
        client.send_ooc('Position reset.')

    # Switching position
    else:
        client.change_position(arg)
        client.area.broadcast_evidence_list()
        client.send_ooc('Position changed.')

def ooc_cmd_randomchar(client, arg):
    """
    Switches the user to a random character.
    Returns an error if new character is available.

    SYNTAX
    /randomchar

    PARAMETERS
    None

    EXAMPLE
    /randomchar
    """

    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    free_id = client.area.get_rand_avail_char_id(allow_restricted=client.is_staff())
    client.change_character(free_id)
    client.send_ooc('Randomly switched to {}'.format(client.get_char_name()))

def ooc_cmd_refresh(client, arg):
    """ (MOD ONLY)
    Reloads the following files for the server: characters, default music list, and background list.

    SYNTAX
    /refresh

    PARAMETERS
    None

    EXAMPLE
    /refresh
    """

    if not client.is_mod:
        raise ClientError('You must be authorized to do that.')
    if len(arg) > 0:
        raise ArgumentError('This command has no arguments.')

    client.server.reload()
    client.send_ooc('You have reloaded the server.')

def ooc_cmd_reload(client, arg):
    """
    Reloads the character for the current user (equivalent to switching to the current character).

    SYNTAX
    /reload

    PARAMETERS
    None

    EXAMPLE
    /reload
    """

    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    client.reload_character()
    client.send_ooc('Character reloaded.')

def ooc_cmd_reload_commands(client, arg):
    """ (MOD ONLY)
    Reloads the commands.py file. Use only if restarting is not a viable option.
    Note that this ONLY updates the contents of this file. If anything you update relies on other
    files (for example, you call a method in client_manager), they will still use the old contents,
    regardless of whatever changes you may have made to the other files.

    SYNTAX
    /reload_commands

    PARAMETERS
    None

    EXAMPLE
    /reload_commands
    """

    if not client.is_mod:
        raise ClientError('You must be authorized to do that.')
    if len(arg) > 0:
        raise ArgumentError('This command has no arguments.')

    outcome = client.server.reload_commands()
    if outcome:
        info = "\n{}: {}".format(type(outcome).__name__, outcome)
        raise ClientError('Server ran into a problem while reloading the commands: {}'.format(info))

    client.send_ooc("The commands have been reloaded.")

def ooc_cmd_remove_h(client, arg):
    """ (MOD ONLY)
    Removes all letter H's from all IC and OOC messages of a player by client ID (number in
    brackets) or IPID (number in parentheses).
    If given IPID, it will affect all clients opened by the user. Otherwise, it will just affect
    the given client.
    Requires /unremove_h to undo.
    Returns an error if the given identifier does not correspond to a user.

    SYNTAX
    /remove_h <client_id>
    /remove_h <client_ipid>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)
    <client_ipid>: IPID for the client (number in parentheses in /getarea)

    EXAMPLES
    /remove_h 1           :: Has all messages sent by the player whose client ID is 1 have their H's removed.
    /remove_h 1234567890  :: Has all messages sent by all clients opened by the user whose IPID is 1234567890 have their H's removed.
    """

    if not client.is_mod:
        raise ClientError('You must be authorized to do that.')

    # Removes H's to matching targets
    for c in Constants.parse_id_or_ipid(client, arg):
        c.remove_h = True
        logger.log_server('Removing h from {}.'.format(c.ipid), client)
        client.area.broadcast_ooc("Removed h from {}.".format(c.displayname))

def ooc_cmd_reveal(client, arg):
    """ (STAFF ONLY)
    Sets given user based on client ID or IPID to no longer be sneaking so that they are visible
    through /getarea(s).
    If given IPID, it will affect all clients opened by the user. Otherwise, it will just affect
    the given client.
    Requires /sneak to undo.
    Returns an error if the given identifier does not correspond to a user.

    SYNTAX
    /reveal <client_id>
    /reveal <client_ipid>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)
    <client_ipid>: IPID for the client (number in parentheses in /getarea)

    EXAMPLES
    /reveal 1                     :: Set client whose ID is 1 to no longer be sneaking.
    /reveal 1234567890            :: Set all clients opened by the user whose IPID is 1234567890 to no longer be sneaking.
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')

    # Unsneak matching targets
    for c in Constants.parse_id_or_ipid(client, arg):
        if c != client:
            client.send_ooc("{} is no longer sneaking.".format(c.displayname))
        c.change_visibility(True)

def ooc_cmd_roll(client, arg):
    """
    Rolls a given number of dice with given number of faces and modifiers. If certain parameters
    are not given, command assumes preset defaults. The result is broadcast to all players in the
    area as well as staff members who have turned foreign roll notifications with /toggle_allrolls.
    The roll is also logged in the client's and area's dice log.
    Returns an error if parameters exceed specified constants or an invalid mathematical operation
    is put as a modifier.

    For modifiers, the modifier's result will ignore the given number of faces cap and instead use
    NUMFACES_MAX (so dice rolls can exceed number of faces). However, the modifier's result is
    bottom capped at 1 (so non-positive values are not allowed). Modifiers follow PEMDAS, and if
    not given the dice result (character "r"), will try and perform the operation directly.

    SYNTAX
    /roll {num_faces} {modifier}
    /roll {num_dice}d<num_faces> {modifier}

    OPTIONAL PARAMETERS
    {num_faces}: Number of faces the dice will have (capped at NUMFACES_MAX).
    {num_dice}: Number of dice to roll (capped at NUMDICE_MAX).
    {modifier}: Operation to perform on rolls.

    EXAMPLES
    Assuming DEF_NUMDICE = 1, DEF_NUMFACES = 6, DEF_MODIFIER = ''...
    /roll               :: Rolls a d6.
    /roll 20            :: Rolls a d20.
    /roll 5d30          :: Rolls 5 d30's.
    /roll d20 +3        :: Rolls a d20 and adds 3 to the result.
    /roll 1d20 +3*2     :: Rolls a d20 and adds 3*2=6 to the result.
    /roll 6 -1+3*r      :: Rolls a d6, multiplies the result by 3 and subtracts 1 to it.
    /roll 3d6 (-1+3)*r  :: Rolls 3 d6's and multiplies each result by 2.
    """

    roll_result, num_faces = Constants.dice_roll(arg, 'roll', client.server)
    roll_message = 'rolled {} out of {}'.format(roll_result, num_faces)
    client.send_ooc('You {}.'.format(roll_message))
    client.send_ooc_others('{} {}.'.format(client.displayname, roll_message), in_area=True)
    client.send_ooc_others('(X) {} {} in {} ({}).'
                           .format(client.displayname, roll_message, client.area.name,
                                   client.area.id), is_staff=True, in_area=False,
                           pred=lambda c: c.get_foreign_rolls)
    client.add_to_dicelog(roll_message + '.')
    client.area.add_to_dicelog(client, roll_message + '.')
    logger.log_server('[{}][{}]Used /roll and got {} out of {}.'
                      .format(client.area.id, client.get_char_name(), roll_result, num_faces), client)

def ooc_cmd_rollp(client, arg):
    """
    Similar to /roll, but instead announces roll results (and who rolled) only to yourself and
    staff members who are in the area or who have foreign roll notifications with /toggle_allrolls.
    The roll is also logged in the client's and area's dice log, but marked as private.
    Returns an error if current area does not authorize /rollp and user is not logged in.

    SYNTAX
    /rollp {num_faces} {modifier}
    /rollp {num_dice}d<num_faces> {modifier}

    OPTIONAL PARAMETERS
    {num_faces}: Number of faces the dice will have (capped at NUMFACES_MAX).
    {num_dice}: Number of dice to roll (capped at NUMDICE_MAX).
    {modifier}: Operation to perform on rolls.

    EXAMPLES
    Assuming DEF_NUMDICE = 1, DEF_NUMFACES = 6, DEF_MODIFIER = ''...
    /rollp               :: Rolls a d6.
    /rollp 20            :: Rolls a d20.
    /rollp 5d30          :: Rolls 5 d30's.
    /rollp d20 +3        :: Rolls a d20 and adds 3 to the result.
    /rollp 1d20 +3*2     :: Rolls a d20 and adds 3*2=6 to the result.
    /rollp 6 -1+3*r      :: Rolls a d6, multiplies the result by 3 and subtracts 1 to it.
    /rollp 3d6 (-1+3)*r  :: Rolls 3 d6's and multiplies each result by 2.
    """

    if not client.area.rollp_allowed and not client.is_staff():
        raise ClientError('This command has been restricted to authorized users only in this area.')

    roll_result, num_faces = Constants.dice_roll(arg, 'rollp', client.server)
    roll_message = 'privately rolled {} out of {}'.format(roll_result, num_faces)
    client.send_ooc('You {}.'.format(roll_message))
    client.send_ooc_others('Someone rolled.', is_staff=False, in_area=True)
    client.send_ooc_others('(X) {} {}.'.format(client.displayname, roll_message),
                           is_staff=True, in_area=True)
    client.send_ooc_others('(X) {} {} in {} ({}).'
                           .format(client.displayname, roll_message, client.area.name,
                                   client.area.id), is_staff=True, in_area=False,
                           pred=lambda c: c.get_foreign_rolls)
    client.add_to_dicelog(roll_message + '.')
    client.area.add_to_dicelog(client, roll_message + '.')

    SALT = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
    encoding = hashlib.sha1((str(roll_result) + SALT).encode('utf-8')).hexdigest() + '|' + SALT
    logger.log_server('[{}][{}]Used /rollp and got {} out of {}.'
                      .format(client.area.id, client.get_char_name(), encoding, num_faces), client)

def ooc_cmd_rplay(client, arg):
    """ (STAFF ONLY)
    Plays a given track in currently reachable areas, even if not explicitly in the music list.
    It is the way to play custom music in multiple areas.

    SYNTAX
    /rplay <track_name>

    PARAMETERS
    <track_name>: Track to play

    EXAMPLES
    /rplay Trial(AJ).mp3         :: Plays Trial(AJ).mp3
    /rplay CustomTrack.mp3       :: Plays CustomTrack.mp3 (will only be audible to users with CustomTrack.mp3)
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')
    if len(arg) == 0:
        raise ArgumentError('You must specify a song.')

    for reachable_area_name in client.area.reachable_areas:
        reachable_area = client.server.area_manager.get_area_by_name(reachable_area_name)
        reachable_area.play_music(arg, client.char_id, -1)
        reachable_area.add_music_playing(client, arg)
        logger.log_server('[{}][{}]Changed music to {}.'
                          .format(client.area.id, client.get_char_name(), arg), client)

def ooc_cmd_rpmode(client, arg):
    """ (STAFF ONLY)
    Toggles RP mode on/off in the server. If turned on, all non-logged in users will be subject to
    RP rules. Some effects include: unable to use /getarea and /getareas in areas that disable it.

    SYNTAX
    /rpmode <new_status>

    PARAMETERS
    <new_status>: 'on' or 'off'

    EXAMPLES
    /rpmode on              :: Turns on RP mode
    /rpmode off             :: Turns off RP mode
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')
    if not client.server.config['rp_mode_enabled']:
        raise ClientError("RP mode is disabled in this server.")
    if len(arg) == 0:
        raise ArgumentError('You must specify either on or off.')

    if arg == 'on':
        client.server.rp_mode = True
        for c in client.server.client_manager.clients:
            c.send_ooc('RP mode enabled.')
            if not c.is_staff():
                c.in_rp = True
    elif arg == 'off':
        client.server.rp_mode = False
        for c in client.server.client_manager.clients:
            c.send_ooc('RP mode disabled.')
            c.in_rp = False
    else:
        client.send_ooc('Expected on or off.')

def ooc_cmd_scream(client, arg):
    """
    Sends a message in the OOC chat visible to all staff members and non-deaf users that are in an
    area whose screams are reachable from the sender's area. It also sends an IC message with the
    scream message.
    If the user is gagged, a special message is instead sent to non-deaf players in the same area.
    If a recipient is deaf, they receive a special OOC message and a blank IC message.
    Staff always get normal messages.
    Returns an error if the user has global chat off or sends an empty message.

    SYNTAX
    /scream <message>

    PARAMETERS
    <message>: Message to be sent

    EXAMPLE
    /scream Hello World      :: Sends Hello World to users in scream reachable areas+staff.
    """

    if client.muted_global:
        raise ClientError('You have the global chat muted.')
    if not arg:
        raise ArgumentError("You cannot send an empty message.")

    if not client.is_gagged:
        client.send_ooc('You screamed "{}".'.format(arg))

        client.send_ooc_others(arg, username="<dollar>SCREAM[{}]".format(client.displayname),
                               is_staff=False, to_deaf=False,
                               pred=lambda c: (not c.muted_global and
                                               (c.area == client.area or
                                                c.area.name in client.area.scream_range)))
        client.send_ooc_others('Your ears are ringing.', is_staff=False, to_deaf=True,
                               pred=lambda c: (not c.muted_global and
                                               (c.area == client.area or
                                                c.area.name in client.area.scream_range)))
        client.send_ooc_others('(X) {} screamed "{}" ({}).'
                               .format(client.displayname, arg, client.area.id),
                               is_staff=True, pred=lambda c: not c.muted_global)

        client.send_ic_others(msg=arg, to_deaf=False,
                              pred=lambda c: (not c.muted_global and
                                              (c.area == client.area or
                                               c.area.name in client.area.scream_range)))
        client.send_ic_others(msg='', to_deaf=True,
                              pred=lambda c: (not c.muted_global and
                                              (c.area == client.area or
                                               c.area.name in client.area.scream_range)))
    else:
        client.send_ooc('You attempted to scream but you have no mouth.')
        client.send_ooc_others('You hear some grunting noises.', is_staff=False, to_deaf=False,
                               in_area=True, pred=lambda c: not c.muted_global)
        # Deaf players get no notification on a gagged player screaming
        client.send_ooc_others('(X) {} attempted to scream "{}" while gagged ({}).'
                               .format(client.displayname, arg, client.area.id),
                               is_staff=True, pred=lambda c: not c.muted_global)

    logger.log_server('[{}][{}][SCREAM]{}.'.format(client.area.id, client.get_char_name(), arg),
                      client)

def ooc_cmd_scream_range(client, arg):
    """ (STAFF ONLY)
    Returns the current area's scream range (i.e. users in which areas who would hear a /scream from
    the current area).

    SYNTAX
    /scream_range

    PARAMETERS
    None

    EXAMPLES
    /scream_range           :: Obtain the current area's scream range, for example {'Basement'}
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')
    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    info = '== Areas in scream range of area {} =='.format(client.area.name)
    # If no areas in scream range, print a manual message.
    if len(client.area.scream_range) == 0:
        info += '\r\n*No areas.'
    # Otherwise, build the list of all areas.
    else:
        for area in client.area.scream_range:
            info += '\r\n*({}) {}'.format(client.server.area_manager.get_area_by_name(area).id, area)

    client.send_ooc(info)

def ooc_cmd_scream_set(client, arg):
    """ (STAFF ONLY)
    Toggles the ability of ONE given area by name or ID to hear a scream from the current area on
    or off. This only modifies the given area's status in the current area's scream range, unlike
    /scream_set_range. Note that scream ranges are unidirectional, so if you want two areas to hear
    one another, you must use this command twice.
    Returns an error if an invalid area name or area ID is given, or if the current area is the
    target of the selection.

    SYNTAX
    /scream_set <target_area>

    PARAMETERS
    <target_area>: The area whose ability to hear screams from the current area must be switched.

    EXAMPLES
    Assuming Area 2: Class Trial Room, 2 starts as not part of the current area's (say Basement) scream range...
    /scream_set Class Trial Room,\ 2 :: Adds "Class Trial Room, 2" to the scream range of Basement (note the \ escape character)-
    /scream_set 2                    :: Removes "Class Trial Room, 2" from the scream range of Basement.
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')
    if len(arg) == 0:
        raise ArgumentError('This command takes one area name.')

    # This should just return a list with one area
    intended_area = Constants.parse_area_names(client, arg.split(', '))
    if len(intended_area) > 1:
        raise ArgumentError('This command takes one area name (did you mean /scream_set_range ?).')

    intended_area = intended_area[0] # Convert the one element list into the area name
    if intended_area == client.area:
        raise ArgumentError('You cannot add or remove the current area from the scream range.')

    # If intended area not in range, add it
    if intended_area.name not in client.area.scream_range:
        client.area.scream_range.add(intended_area.name)
        client.send_ooc('Added area {} to the scream range of area {}.'
                        .format(intended_area.name, client.area.name))
        client.send_ooc_others('(X) {} added area {} to the scream range of area {} ({}).'
                               .format(client.displayname, intended_area.name, client.area.name,
                                       client.area.id), is_staff=True)
        logger.log_server('[{}][{}]Added area {} to the scream range of area {}.'
                          .format(client.area.id, client.get_char_name(), intended_area.name,
                                  client.area.name), client)
    else: # Otherwise, add it
        client.area.scream_range.remove(intended_area.name)
        client.send_ooc('Removed area {} from the scream range of area {}.'
                        .format(intended_area.name, client.area.name))
        client.send_ooc_others('(X) {} removed area {} from the scream range of area {} ({}).'
                               .format(client.displayname, intended_area.name, client.area.name,
                                       client.area.id), is_staff=True)
        logger.log_server('[{}][{}]Removed area {} from the scream range of area {}.'
                          .format(client.area.id, client.get_char_name(), intended_area.name,
                                  client.area.name), client)

def ooc_cmd_scream_set_range(client, arg):
    """ (STAFF ONLY)
    Sets the current area's scream range to a given list of areas by name or ID separated by commas.
    This completely overrides the old scream range, unlike /scream_set.
    Passing in no arguments sets the scream range to nothing (i.e. a soundproof room).
    Note that scream ranges are unidirectional, so if you want two areas to hear one another, you
    must use this command twice.
    Returns an error if an invalid area name or area ID is given, or if the current area is part of
    the selection.

    SYNTAX
    /scream_set_range {area_1}, {area_2}, {area_3}, ...

    PARAMETERS
    {area_n}: An area to add to the current scream range. Can be either an area name or area ID.

    EXAMPLES:
    Assuming the current area is Basement...
    /scream_set_range Class Trial Room 3                            :: Sets Basement's scream range to "Class Trial Room 3"
    /scream_set_range Class Trial Room,\ 2, 1, Class Trial Room 3   :: Sets Basement's scream range to "Class Trial Room, 2" (note the \ escape character"), area 1 and "Class Trial Room 3".
    /scream_set_range                                               :: Sets Basement's scream range to no areas.
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')

    if len(arg) == 0:
        client.area.scream_range = set()
        area_names = '{}'
    else:
        areas = Constants.parse_area_names(client, arg.split(', '))
        if client.area in areas:
            raise ArgumentError('You cannot add the current area to the scream range.')
        area_names = {area.name for area in areas}
        client.area.scream_range = area_names

    client.send_ooc('Set the scream range of area {} to be: {}.'
                    .format(client.area.name, area_names))
    client.send_ooc_others('(X) {} set the scream range of area {} to be: {} ({}).'
                           .format(client.displayname, client.area.name, area_names,
                                   client.area.id), is_staff=True)
    logger.log_server('[{}][{}]Set the scream range of area {} to be: {}.'
                      .format(client.area.id, client.get_char_name(), client.area.name, area_names), client)

def ooc_cmd_shoutlog(client, arg):
    """ (STAFF ONLY)
    List the last 20 shouts performed in the current area (Hold it, Objection, Take That, etc.).
    If given an argument, it will return the shoutlog of the given area by ID or name.
    Otherwise, it will obtain the one from the current area.
    Returns an error if the given identifier does not correspond to an area.

    SYNTAX
    /shoutlog {target_area}

    OPTIONAL PARAMETERS
    {target_area}: area whose shoutlog will be returned (either ID or name)

    EXAMPLE
    If currently in the Basement (area 0)...
    /shoutlog           :: You may get something like the next example
    /shoutlog 0         :: You may get something like this

    == Shout log of Basement (0) ==
    *Sat Jun 29 13:15:56 2019 | [1] Phantom (1234567890) used shout 1 with the message: I consent
    *Sat Jun 29 13:16:41 2019 | [1] Phantom (1234567890) used shout 3 with the message: u wrong m9
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')
    if len(arg) == 0:
        arg = client.area.name

    # Obtain matching area's shoutlog
    for area in Constants.parse_area_names(client, [arg]):
        info = area.get_shoutlog()
        client.send_ooc(info)

def ooc_cmd_showname(client, arg):
    """
    If given an argument, sets the client's showname to that. Otherwise, it clears their showname
    to use the default setting (character showname). These custom shownames override whatever client
    showname the current character has, and is persistent between between character swaps, area
    changes, etc.
    Returns an error if new custom showname exceeds the server limit (server parameter
    'showname_max_length', is already used in the current area, or if shownames have been frozen
    and the user is not logged in.

    SYNTAX
    /showname <new_showname>
    /showname

    PARAMETERS
    <new_showname>: New desired showname.

    EXAMPLES
    /showname Phantom       :: Sets your showname to Phantom
    /showname               :: Clears your showname
    """

    if client.server.showname_freeze and not client.is_staff():
        raise ClientError('Shownames are frozen.')

    try:
        client.change_showname(arg, forced=False)
    except ValueError:
        raise ClientError("Given showname {} is already in use in this area.".format(arg))

    if arg != '':
        client.send_ooc('You have set your showname to {}'.format(arg))
        logger.log_server('{} set their showname to {}.'.format(client.ipid, arg), client)
    else:
        client.send_ooc('You have removed your custom showname.')
        logger.log_server('{} removed their showname.'.format(client.ipid), client)

def ooc_cmd_showname_area(client, arg):
    """
    List the characters (and associated client IDs) in the current area, as well as their custom
    shownames if they have one in parentheses.
    Returns an error if the user is subject to RP mode and is in an area that disables /getarea or
    if they are blind.

    SYNTAX
    /showname_area

    PARAMETERS
    None

    EXAMPLE
    /showname_area          :: May list something like this

    == Area 0: Basement ==
    [0] Phantom_HD
    [1] Spam_HD (Spam, Spam, Spam...)
    """

    Constants.command_assert(client, arg, parameters='=0')
    if not client.is_staff() and client.is_blind:
        raise ClientError('You are blind, so you cannot see anything.')

    client.send_area_info(client.area, client.area.id, False, include_shownames=True)

def ooc_cmd_showname_areas(client, arg):
    """
    List the characters (and associated client IDs) in each area, as well as their custom shownames
    if they have one in parentheses.
    Returns an error if the user is subject to RP mode and is in an area that disables /getareas
    or if they are blind.

    SYNTAX
    /showname_areas

    PARAMETERS
    None

    EXAMPLE
    /showname_areas          :: May list something like this

    == Area List ==
    == Area 0: Basement ==
    [0] Phantom_HD
    [1] Spam_HD (Spam, Spam, Spam...)
    == Area 1: Class Trial Room 1 ==
    [2] Eggs_HD (Not Spam?)
    """

    Constants.command_assert(client, arg, parameters='=0')
    if not client.is_staff() and client.is_blind:
        raise ClientError('You are blind, so you cannot see anything.')

    client.send_area_info(client.area, -1, False, include_shownames=True)

def ooc_cmd_showname_freeze(client, arg):
    """ (MOD ONLY)
    Toggles non-staff members being able to use /showname or not.
    It does NOT clear their shownames (see /showname_nuke).
    Staff can still use /showname_set to set shownames of others.

    SYNTAX
    /showname_freeze

    PARAMETERS
    None

    EXAMPLE
    Assuming shownames are not frozen originally...
    /showname_freeze        :: Freezes all shownames. Only staff members can change or remove them.
    /showname_freeze        :: Unfreezes all shownames. Everyone can use /showname again.
    """

    if not client.is_mod:
        raise ClientError('You must be authorized to do that.')
    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    client.server.showname_freeze = not client.server.showname_freeze
    status = {False: 'unfrozen', True: 'frozen'}

    client.send_ooc('You have {} all shownames.'.format(status[client.server.showname_freeze]))
    client.send_ooc_others('A mod has {} all shownames.'
                           .format(status[client.server.showname_freeze]), is_mod=False)
    client.send_ooc_others('{} has {} all shownames.'
                           .format(client.name, status[client.server.showname_freeze]), is_mod=True)
    logger.log_server('{} has {} all shownames.'
                      .format(client.name, status[client.server.showname_freeze]), client)

def ooc_cmd_showname_history(client, arg):
    """ (MOD ONLY)
    List all shownames a client by ID or IPID has had during the session. Output differentiates
    between self-initiated showname changes (such as the ones via /showname) by using "Self"
    and third-party-initiated ones by using "Was" (such as /showname_set, or by changing areas and
    having a showname conflict).

    If given IPID, it will obtain the showname history of all the clients opened by the user.
    Otherwise, it will just obtain the showname history of the given client.
    Returns an error if the given identifier does not correspond to a user.

    SYNTAX
    /showname_history <client_id>
    /showname_history <client_ipid>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)
    <client_ipid>: IPID for the client (number in parentheses in /getarea)

    EXAMPLE
    /showname_history 1         :: For the client whose ID is 1, you may get something like this

    == Showname history of client 1 ==
    *Sat Jun 1 18:52:32 2019 | Self set to Cas
    *Sat Jun 1 18:52:56 2019 | Was set to NotCas
    *Sat Jun 1 18:53:47 2019 | Was set to Ces
    *Sat Jun 1 18:53:54 2019 | Self cleared
    *Sat Jun 1 18:54:36 2019 | Self set to Cos
    *Sat Jun 1 18:54:46 2019 | Was cleared
    """

    if not client.is_mod:
        raise ClientError('You must be authorized to do that.')

    # Obtain matching targets's showname history
    for c in Constants.parse_id_or_ipid(client, arg):
        info = c.get_showname_history()
        client.send_ooc(info)

def ooc_cmd_showname_nuke(client, arg):
    """ (MOD ONLY)
    Clears all shownames from non-staff members.

    SYNTAX
    /showname_nuke

    PARAMETERS
    None

    EXAMPLE
    /showname_nuke          :: Clears all shownames
    """

    if not client.is_mod:
        raise ClientError('You must be authorized to do that.')
    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    for c in client.server.client_manager.clients:
        if not c.is_staff() and c.showname != '':
            c.change_showname('')

    client.send_ooc('You have nuked all shownames.')
    client.send_ooc_others('A mod has nuked all shownames.', is_mod=False)
    client.send_ooc_others('{} has nuked all shownames.'.format(client.name), is_mod=True)
    logger.log_server('{} has nuked all shownames.'.format(client.name), client)

def ooc_cmd_showname_set(client, arg):
    """ (STAFF ONLY)
    If given a second argument, sets the showname of the given client by ID or IPID to that.
    Otherwise, it clears their showname to use the default setting (character showname).
    These custom shownames override whatever showname the current character has, and is persistent
    between between character swaps/area changes/etc.
    If given IPID, it will set the shownames of all the clients opened by the user. Otherwise, it
    will just set the showname of the given client.
    Returns an error if the given identifier does not correspond to a user.

    SYNTAX
    /showname_set <client_id> {new_showname}
    /showname_set <client_ipid> {new_showname}

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)
    <client_ipid>: IPID for the client (number in parentheses in /getarea)
    {new_showname}: New desired showname.

    EXAMPLES
    /showname_set 1 Phantom     :: Sets the showname of the client whose ID is 1 to Phantom.
    /showname_set 1234567890    :: Clears the showname of the client(s) whose IPID is 1234567890.
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')

    try:
        separator = arg.index(" ")
    except ValueError:
        separator = len(arg)

    ID = arg[:separator]
    showname = arg[separator+1:]

    # Set matching targets's showname
    for c in Constants.parse_id_or_ipid(client, ID):
        try:
            c.change_showname(showname)
        except ValueError:
            raise ClientError("Unable to set the showname of {}: Given showname {} is already in "
                              "use in area {}.".format(c.get_char_name(), showname, c.area.name))

        if showname != '':
            logger.log_server('Set showname of {} to {}.'.format(c.ipid, showname), client)
            client.send_ooc('Set showname of {} to {}.'.format(c.get_char_name(), showname))
            c.send_ooc("Your showname was set to {} by a staff member.".format(showname))
        else:
            logger.log_server('Removed showname {} of {}.'.format(showname, c.ipid), client)
            client.send_ooc('Removed showname {} of {}.'.format(showname, c.get_char_name()))
            c.send_ooc("Your showname was removed by a staff member.")

def ooc_cmd_sneak(client, arg):
    """ (STAFF ONLY)
    Sets given user based on client ID or IPID to be sneaking so that they are invisible through
    /getarea(s), /showname_list and /area.
    If given IPID, it will affect all clients opened by the user. Otherwise, it will just affect
    the given client.
    Requires /reveal to undo.
    Returns an error if the given identifier does not correspond to a user.

    SYNTAX
    /sneak <client_id>
    /sneak <client_ipid>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)
    <client_ipid>: IPID for the client (number in parentheses in /getarea)

    EXAMPLES
    /sneak 1                     :: Set client whose ID is 1 to be sneaking.
    /sneak 1234567890            :: Set all clients opened by the user whose IPID is 1234567890 to be sneaking.
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')

    # Sneak matching targets
    for c in Constants.parse_id_or_ipid(client, arg):
        if client.is_gm and c.area.lobby_area:
            client.send_ooc('Target client is in a lobby area. You have insufficient permissions '
                            'to hide someone in such an area.')
            continue
        if c.area.private_area:
            client.send_ooc('Target client is in a private area. You are not allowed to hide '
                            'someone in such an area.')
            continue

        if c != client:
            client.send_ooc("{} is now sneaking.".format(c.displayname))
        c.change_visibility(False)

def ooc_cmd_st(client, arg):
    """ (STAFF ONLY)
    Send a message to the private server-wide staff chat. Only staff members can send and receive
    messages from it (i.e. it is not a report command for normal users).

    SYNTAX
    /st <message>

    PARAMETERS
    <message>: Your message

    EXAMPLES
    /st Need help in area 0.       :: Sends "Need help in area 0" to all staff members.
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')

    pre = '{} [Staff] {}'.format(client.server.config['hostname'], client.name)
    client.server.send_all_cmd_pred('CT', pre, arg, pred=lambda c: c.is_staff())
    logger.log_server('[{}][STAFFCHAT][{}][{}]{}.'.format(client.area.id, client.get_char_name(), client.name, arg), client)

def ooc_cmd_switch(client, arg):
    """
    Switches current user's character to a different one.
    Returns an error if character is unavailable or non-existant.

    SYNTAX
    /switch <char_name>

    PARAMETERS
    <char_name>: Character name

    EXAMPLES
    /switch Phoenix_HD
    """

    if len(arg) == 0:
        raise ArgumentError('You must specify a character name.')

    # Obtain char_id if character exists and then try and change to given char if available
    cid = client.server.get_char_id_by_name(arg)
    client.change_character(cid, client.is_mod)
    client.send_ooc('Character changed.')

def ooc_cmd_time(client, arg):
    """
    Return the current server date and time.

    SYNTAX
    /time

    PARAMETERS
    None

    EXAMPLES
    /time           :: May return something like "Sat Apr 27 09:04:17 2019"
    """

    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    client.send_ooc(Constants.get_time())

def ooc_cmd_time12(client, arg):
    """
    Return the current server date and time in 12 hour format.
    Also includes the server timezone.

    SYNTAX
    /time12

    PARAMETERS
    None

    EXAMPLES
    /time12         :: May return something like "Sat Apr 27 09:04:47 AM (EST) 2019"
    """

    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    client.send_ooc(time.strftime('%a %b %e %I:%M:%S %p (%z) %Y'))

def ooc_cmd_timer(client, arg):
    """
    Start a timer.

    SYNTAX
    /timer <length> {timername} {public}

    PARAMETERS
    <length>: time in seconds, or in mm:ss, or in h:mm:ss; limited to TIMER_LIMIT in function
             Constants.parse_time_length

    OPTIONAL PARAMETERS
    {timername}: Timer name; defaults to username+"Timer" if empty
    {public or not}: Whether the timer is public or not; defaults to public if not fed one of
    "False", "false", "0", "No", "no".

    EXAMPLES
    Assuming the player has OOC name Phantom...
    /timer 10               :: Starts a public timer "PhantomTimer" of 10 seconds.
    /timer 3:00 T           :: Starts a public timer "T" of length 3 minutes.
    /timer 5:53:21 Spam No  :: Starts a private timer "Spam" of length 5 hours, 53 mins and 21 secs.

    Public status functionality
    * Non-public timers will only send timer announcements/can only be consulted by
      the person who initiated the timer and staff
    * Public timers initiated by non-staff will only send timer announcements/can only be
      be consulted by staff and people in the same area as the person who initiated the timer
    * Public timers initiated by staff will send timer announcements/can be consulted by
      anyone at any area.
    """

    if len(arg) == 0:
        raise ClientError('This command takes at least one argument.')
    arg = arg.split(' ')
    if len(arg) >= 4:
        raise ClientError('This command takes at most three arguments.')

    # Check if valid length and convert to seconds
    length = Constants.parse_time_length(arg[0]) # Also internally validates

    # Check name
    if len(arg) > 1:
        name = arg[1]
    else:
        name = client.name.replace(" ", "") + "Timer" # No spaces!
    if name in client.server.active_timers.keys():
        raise ClientError('Timer name {} is already taken.'.format(name))

    # Check public status
    if len(arg) > 2 and arg[2] in ['False', 'false', '0', 'No', 'no']:
        is_public = False
    else:
        is_public = True

    client.server.active_timers[name] = client #Add to active timers list
    client.send_ooc('You initiated a timer "{}" of length {} seconds.'.format(name, length))
    client.send_ooc_others('{} initiated a timer "{}" of length {} seconds in area {} ({}).'
                           .format(client.displayname, name, length, client.area.name,
                                   client.area.id), is_staff=True)
    client.send_ooc_others('{} initiated a timer "{}" of length {} seconds.'
                           .format(client.displayname, name, length), is_staff=False,
                           pred=lambda c: is_public)

    client.server.create_task(client, ['as_timer', time.time(), length, name, is_public])

def ooc_cmd_timer_cancel(client, arg):
    """
    Cancel given timer by timer name. Requires logging in to cancel timers initiated by other users.
    Returns an error if timer does not exist or if the user is not authorized to cancel the timer.

    SYNTAX
    /timer_cancel <timername>

    PARAMETERS
    <timername>: Timer name to cancel

    EXAMPLES
    Assuming player Spam started a timer "S", and the moderator Phantom started a timer "P"...
    /timer_cancel S     :: Both Spam and Phantom would cancel timer S if either ran this.
    /timer_cancel P     :: Only Phantom would cancel timer P if either ran this.
    """

    if len(arg) == 0:
        raise ArgumentError('Expected timer name.')
    arg = arg.split(' ')
    if len(arg) != 1:
        raise ClientError('This command variation takes exactly one argument.')

    timer_name = arg[0]
    try:
        timer_client = client.server.active_timers[timer_name]
    except KeyError:
        raise ClientError('Timer {} is not an active timer.'.format(timer_name))

    # Non-staff are only allowed to cancel their own timers
    if not client.is_staff() and client != timer_client:
        raise ClientError('You must be authorized to do that.')

    timer = client.server.get_task(timer_client, ['as_timer'])
    client.server.cancel_task(timer)

def ooc_cmd_timer_get(client, arg):
    """
    Get remaining time from given timer if given a timer name. Otherwise, list all viewable timers.
    Returns an error if user attempts to consult a timer they have no permissions for.

    SYNTAX
    /timer_get {timername}

    OPTIONAL PARAMETERS
    {timername}: Check time remaining in given timer; defaults to all timers if not given one.

    EXAMPLES
    Assuming a player Spam started a private timer "S", a moderator Phantom started a timer "P",
    and a third player Eggs started a public timer "E"...
    /timer_get      :: Spam and Phantom would get the remaining times of S, P and E; Eggs only S and P.
    /timer_get S    :: Spam and Phantom would get the remaining time of S, Eggs would get an error.
    /timer_get P    :: Spam, Phantom and Eggs would get the remaining time of P.
    /timer_get E    :: Spam, Phantom and Eggs would get the remaining time of E.
    """

    arg = arg.split(' ') if arg else list()
    if len(arg) > 1:
        raise ClientError('This command takes at most one argument.')

    string_of_timers = ""

    if len(arg) == 1:
        # Check specific timer
        timer_name = arg[0]
        if timer_name not in client.server.active_timers.keys():
            raise ClientError('Timer {} is not an active timer.'.format(timer_name))
        timers_to_check = [timer_name]
    else: # Case len(arg) == 0
        # List all timers
        timers_to_check = client.server.active_timers.keys()
        if len(timers_to_check) == 0:
            raise ClientError('No active timers.')

    for timer_name in timers_to_check:
        timer_client = client.server.active_timers[timer_name]
        start, length, _, is_public = client.server.get_task_args(timer_client, ['as_timer'])

        # Non-public timers can only be consulted by staff and the client who started the timer
        if not is_public and not (client.is_staff() or client == timer_client):
            continue

        # Non-staff initiated public timers can only be consulted by all staff and
        # clients in the same area as the timer initiator
        elif (is_public and not timer_client.is_staff() and not
              (client.is_staff() or client == timer_client or client.area == timer_client.area)):
            continue

        _, remain_text = Constants.time_remaining(start, length)
        string_of_timers += 'Timer {} has {} remaining.\n*'.format(timer_name, remain_text)

    if string_of_timers == "": # No matching timers
        if len(arg) == 1: # Checked for a specific timer
            # This case happens when a non-authorized user attempts to check
            # a non-public timer
            string_of_timers = "Timer {} is not an active timer.  ".format(timer_name)
            # Double space intentional
        else: # len(arg) == 0
            # This case happens when a non-authorized user attempts to check
            # all timers and all timers are non-public or non-viewable.
            string_of_timers = "No timers available.  " # Double space intentional
    elif len(arg) == 0: # Used /timer_get
        string_of_timers = "Current active timers:\n*" + string_of_timers # Add lead

    client.send_ooc(string_of_timers[:-2]) # Ignore last newline character

def ooc_cmd_ToD(client, arg):
    """
    Chooses "Truth" or "Dare". Intended to be use for participants in Truth or Dare games.

    SYNTAX
    /ToD

    PARAMETERS
    None

    EXAMPLES
    /ToD                :: May return something like 'Phoenix_HD has to do a truth.'
    """

    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    coin = ['truth', 'dare']
    flip = random.choice(coin)
    client.area.broadcast_ooc('{} has to do a {}.'.format(client.displayname, flip))
    logger.log_server('[{}][{}]has to do a {}.'
                      .format(client.area.id, client.get_char_name(), flip), client)

def ooc_cmd_toggle_allrolls(client, arg):
    """ (STAFF ONLY)
    Toggles receiving /roll and /rollp notifications from areas other than the current one.
    Notifications are turned off by default.

    SYNTAX
    /toggle_allrolls

    PARAMETERS
    None

    EXAMPLE
    /toggle_allrolls
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')
    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    client.get_foreign_rolls = not client.get_foreign_rolls
    status = {False: 'no longer', True: 'now'}

    client.send_ooc('You are {} receiving roll results from other areas.'
                    .format(status[client.get_foreign_rolls]))

def ooc_cmd_toggle_fp(client, arg):
    """
    Toggles first person mode on or off. If on, you will not receive your character sprites when you
    send messages yourself, but instead will keep whatever the last sprite used was onscreen.

    SYNTAX
    /toggle_fp

    PARAMETERS
    None

    EXAMPLE
    Assuming you start in normal mode...
    /toggle_fp          :: Toggles first person mode on.
    /toggle_fp          :: Toggles first person mode off.
    """

    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    client.first_person = not client.first_person
    status = {True: 'now', False: 'no longer'}

    client.send_ooc('You are {} in first person mode.'.format(status[client.first_person]))

def ooc_cmd_toggle_global(client, arg):
    """
    Toggles global messages being sent to the current user being allowed/disallowed.

    SYNTAX
    /toggle_global

    PARAMETERS
    None

    EXAMPLE
    /toggle_global
    """

    Constants.command_assert(client, arg, parameters='=0')

    client.muted_global = not client.muted_global
    status = {True: 'no longer', False: 'now'}

    client.send_ooc('You will {} receive global messages.'.format(status[client.muted_global]))

def ooc_cmd_toggle_pm(client, arg):
    """
    Toggles between being able to receive PMs or not.

    SYNTAX
    /toggle_pm

    PARAMETERS
    None

    EXAMPLE
    /toggle_pm
    """

    Constants.command_assert(client, arg, parameters='=0')

    client.pm_mute = not client.pm_mute
    status = {True: 'You will no longer receive PMs.', False: 'You will now receive PMs.'}

    client.send_ooc(status[client.pm_mute])

def ooc_cmd_toggle_shownames(client, arg):
    """
    Toggles between receiving IC messages with custom shownames or receiving them all with
    character names. When joining, players will receive IC messages with shownames.

    SYNTAX
    /toggle_shownames

    PARAMETERS
    None

    EXAMPLE
    Assuming a player who just joined
    /toggle_shownames           :: All subsequent messages will only include character names as the message sender.
    /toggle_shownames           :: All subsequent messages will include the shownames of the senders if they have one.
    """

    if len(arg) != 0:
        raise ArgumentError("This command has no arguments.")

    client.show_shownames = not client.show_shownames
    status = {False: 'off', True: 'on'}

    client.send_ooc('Shownames turned {}.'.format(status[client.show_shownames]))

def ooc_cmd_transient(client, arg):
    """ (STAFF ONLY)
    Toggles a client by IP or IPID being transient or not to passage locks (i.e. can access all
    areas or only reachable areas)
    If given IPID, it will invert the transient status of all the clients opened by the user.
    Otherwise, it will just do it to the given client.
    Returns an error if the given identifier does not correspond to a user.

    SYNTAX
    /transient <client_id>
    /transient <client_ipid>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)
    <client_ipid>: IPID for the client (number in parentheses in /getarea)

    EXAMPLE
    Assuming a player with client ID 0 and IPID 1234567890 starts as not being transient to passage locks
    /transient 0            :: This player can now access all areas regardless of passage locks.
    /transient 1234567890   :: This player can now only access only reachable areas.
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')

    # Invert current transient status of matching targets
    status = {False: 'no longer', True: 'now'}
    for c in Constants.parse_id_or_ipid(client, arg):
        c.is_transient = not c.is_transient
        client.send_ooc('{} ({}) is {} transient to passage locks.'
                        .format(c.displayname, c.area.id, status[c.is_transient]))
        c.send_ooc('You are {} transient to passage locks.'.format(status[c.is_transient]))
        c.reload_music_list() # Update their music list to reflect their new status

def ooc_cmd_unban(client, arg):
    """ (MOD ONLY)
    Removes given user from the server banlist, allowing them to rejoin the server.
    Returns an error if given IPID does not correspond to a banned user.

    SYNTAX
    /unban <client_ipid>

    PARAMETERS
    <client_ipid>: IPID for the client (number in parentheses in /getarea)

    EXAMPLES
    /unban 1234567890           :: Unbans user whose IPID is 1234567890
    """

    if not client.is_mod:
        raise ClientError('You must be authorized to do that.')

    # Assumes that any error is caused by putting something other than an IPID.
    try:
        client.server.ban_manager.remove_ban(int(arg.strip()))
    except Exception:
        raise ClientError('You must specify \'IPID\'')

    logger.log_server('Unbanned {}.'.format(arg), client)
    client.send_ooc('Unbanned {}'.format(arg))

def ooc_cmd_unbanhdid(client, arg):
    """ (MOD ONLY)
    Removes given user by HDID from the server banlist, allowing them to rejoin the server.
    Returns an error if given HDID does not correspond to a banned user.

    SYNTAX
    /unbanhdid <client_hdid>

    PARAMETERS
    <client_hdid>: User HDID (available in server logs and through a mod /whois)

    EXAMPLES
    /unbanhdid abcd1234         :: Unbans user whose HDID is abcd1234
    """

    Constants.command_assert(client, arg, parameters='=1', is_mod=True)

    if not arg in client.server.hdid_list:
        raise ClientError('Unrecognized HDID {}.'.format(arg))

    # The server checks for any associated banned IPID for a player, so in order to unban by HDID
    # all the associated IPIDs must be unbanned.

    found_banned = False
    for ipid in client.server.hdid_list[arg]:
        if client.server.ban_manager.is_banned(ipid):
            client.server.ban_manager.remove_ban(ipid)
            found_banned = True

    if not found_banned:
        raise ClientError('Player was not banned.')

    logger.log_server('Unbanned {}.'.format(arg), client)
    client.send_ooc('Unbanned {}.'.format(arg))

def ooc_cmd_unblockdj(client, arg):
    """ (CM AND MOD ONLY)
    Restores the ability of a player by client ID (number in brackets) or IPID (number in
    parentheses) to change music.
    If given IPID, it will affect all clients opened by the user. Otherwise, it will just affect
    the given client.
    Returns an error if the given identifier does not correspond to a user.

    SYNTAX
    /unblockdj <client_id>
    /unblockdj <client_ipid>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)
    <client_ipid>: IPID for the client (number in parentheses in /getarea)

    EXAMPLES
    /unblockdj 1                     :: Restores DJ permissions to the client whose ID is 1.
    /unblockdj 1234567890            :: Restores DJ permissions to all clients opened by the user whose IPID is 1234567890.
    """

    if not client.is_mod and not client.is_cm:
        raise ClientError('You must be authorized to do that.')

    # Restore DJ permissions to matching targets
    for c in Constants.parse_id_or_ipid(client, arg):
        c.is_dj = True
        logger.log_server('Restored DJ permissions to {}.'.format(c.ipid), client)
        client.area.broadcast_ooc("{} was restored DJ permissions.".format(c.displayname))

def ooc_cmd_undisemconsonant(client, arg):
    """ (MOD ONLY)
    Removes the disemconsonant effect on all IC and OOC messages of a player by client ID
    (number in brackets) or IPID (number in parentheses).
    If given IPID, it will affect all clients opened by the user. Otherwise, it will just affect
    the given client.
    Requires /disemconsonant to undo.
    Returns an error if the given identifier does not correspond to a user.

    SYNTAX
    /undisemconsonant <client_id>
    /undisemconsonant <client_ipid>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)
    <client_ipid>: IPID for the client (number in parentheses in /getarea)

    EXAMPLES
    /undisemconsonant 1           :: Undisemconsonants the player whose client ID is 1.
    /undisemconsonant 1234567890  :: Undisemconsonants all clients opened by the user whose IPID is 1234567890.
    """

    if not client.is_mod:
        raise ClientError('You must be authorized to do that.')

    # Undisemconsonant matching targets
    for c in Constants.parse_id_or_ipid(client, arg):
        c.disemconsonant = False
        logger.log_server('Undisemconsonanted {}.'.format(c.ipid), client)
        client.area.broadcast_ooc("{} was undisemconsonanted.".format(c.displayname))

def ooc_cmd_undisemvowel(client, arg):
    """ (MOD ONLY)
    Removes the disemvowel effect on all IC and OOC messages of a player by client ID (number in
    brackets) or IPID (number in parentheses).
    If given IPID, it will affect all clients opened by the user. Otherwise, it will just affect
    the given client.
    Requires /disemvowel to undo.
    Returns an error if the given identifier does not correspond to a user.

    SYNTAX
    /undisemvowel <client_id>
    /undisemvowel <client_ipid>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)
    <client_ipid>: IPID for the client (number in parentheses in /getarea)

    EXAMPLES
    /undisemvowel 1           :: Undisemvowel the player whose client ID is 1.
    /undisemvowel 1234567890  :: Undisemvowel all clients opened by the user whose IPID is 1234567890.
    """

    if not client.is_mod:
        raise ClientError('You must be authorized to do that.')

    # Undisemvowel matching targets
    for c in Constants.parse_id_or_ipid(client, arg):
        c.disemvowel = False
        logger.log_server('Undisemvowelled {}.'.format(c.ipid), client)
        client.area.broadcast_ooc("{} was undisemvowelled.".format(c.displayname))

def ooc_cmd_unfollow(client, arg):
    """ (STAFF ONLY)
    Stops following the player you are following.
    Returns an error if you are not following anyone.

    SYNTAX
    /unfollow

    PARAMETERS
    None

    EXAMPLE
    Assuming you were following someone...
    /unfollow                     :: Stops following the player
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')
    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    client.unfollow_user()

def ooc_cmd_ungimp(client, arg):
    """ (MOD ONLY)
    Ungimps all IC messages of a player by client ID (number in brackets) or IPID (number in
    parentheses).
    If given IPID, it will affect all clients opened by the user. Otherwise, it will just affect
    the given client.
    Requires /gimp to undo.
    Returns an error if the given identifier does not correspond to a user.

    SYNTAX
    /ungimp <client_id>
    /ungimp <client_ipid>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)
    <client_ipid>: IPID for the client (number in parentheses in /getarea)

    EXAMPLES
    /ungimp 1                     :: Gimps the player whose client ID is 1.
    /ungimp 1234567890            :: Gimps all clients opened by the user whose IPID is 1234567890.
    """

    if not client.is_mod:
        raise ClientError('You must be authorized to do that.')

    # Ungimp matching targets
    for c in Constants.parse_id_or_ipid(client, arg):
        c.gimp = False
        logger.log_server('Ungimping {}.'.format(c.ipid), client)
        client.area.broadcast_ooc("{} was ungimped.".format(c.displayname))

def ooc_cmd_unglobalic(client, arg):
    """ (STAFF ONLY)
    Send subsequent IC messages to users in the same area as the client (i.e. as normal).
    It is the way to undo a /globalic command.

    SYNTAX
    /unglobalic

    PARAMETERS
    None

    EXAMPLES
    /unglobalic             :: Send subsequent messages normally (only to users in current area).
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')
    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    client.multi_ic = None
    client.send_ooc('Your IC messages will now be only sent to your current area.')

def ooc_cmd_unhandicap(client, arg):
    """ (STAFF ONLY)
    Removes movement handicaps on a client by ID or IPID so that they no longer need to wait a set
    amount of time between changing areas. This will also remove server handicaps, if any (such as
    automatic sneak handicaps).
    If given IPID, it will remove the movement handicap on all the clients opened by the user.
    Otherwise, it will just do it to the given client.
    Requires /handicap to undo.
    Returns an error if the given identifier does not correspond to a user.

    SYNTAX
    /unhandicap <client_id>
    /unhandicap <client_ipid>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)
    <client_ipid>: IPID for the client (number in parentheses in /getarea)

    EXAMPLES
    /unhandicap 0           :: Removes all movement handicaps on the player whose client ID is 0
    /unhandicap 1234567890  :: Removes all movement handicaps on the clients whose IPID is 1234567890
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')

    # Obtain targets
    for c in Constants.parse_id_or_ipid(client, arg):
        try:
            _, _, name, _ = client.server.get_task_args(c, ['as_handicap'])
        except KeyError:
            client.send_ooc('{} does not have an active movement handicap.'
                            .format(c.displayname))
        else:
            client.send_ooc('You removed the movement handicap "{}" on {}.'
                            .format(name, c.displayname))
            client.send_ooc_others('(X) {} removed the movement handicap "{}" on {} in area {} ({}).'
                                   .format(client.name, name, c.displayname, client.area.name,
                                           client.area.id), is_staff=True)
            c.send_ooc('Your movement handicap "{}" when changing areas was removed.'.format(name))
            c.handicap_backup = None
            client.server.remove_task(c, ['as_handicap'])

def ooc_cmd_unilock(client, arg):
    """ (VARYING REQUIREMENTS)
    Changes the passage status from a given area to another by name or ID. Passages are
    unidirectional, so to change a passage in both directions simultaneously, use /bilock instead.
    If given one area, it will change the passage status FROM the current area TO the given one.
    If given two areas instead, it  will change the passage status FROM the first given area TO
    the second give one (but requires staff role to use).
    Returns an error if the user is unauthorized to create new passages or change existing ones in
    the originating area. In particular, non-staff members are not allowed to create passages
    that did not exist when the areas were loaded or that a staff member did not create before.

    SYNTAX
    /unilock <target_area>
    /unilock <target_area_1>, <target_area_2>

    PARAMETERS
    <target_area>: Area whose passage status that starts in the current area will be changed.
    <target_area_1>: Area whose passage status that ends in <target_area_2> will be changed.
    <target_area_2>: Area whose passage status that starts in <target_area_1> will be changed.

    EXAMPLES
    Assuming the player is in area 0 when executing these commands and originally the only existing
    passage lock is from area 1 'Class Trial Room' to area 2 'Class Trial Room, 2'...
    /unilock Class Trial Room            :: Locks the passage from area 0 to Class Trial Room.
    /unilock 1, 2                        :: Unlocks the passage from Class Trial Room to Class Trial
                                            Room, 2 (keeps it unlocked the other way).
    /unilock Class Trial Room,\ 2, 0     :: Locks the passage in from Class Trial Room, 2 to area 0
                                            (note the ,\ in the command).
    """

    areas = arg.split(', ')
    if len(areas) > 2 or arg == '':
        raise ArgumentError('This command takes one or two arguments.')
    if len(areas) == 2 and not client.is_staff():
        raise ClientError('You must be authorized to use the two-parameter version of this command.')

    areas = Constants.parse_two_area_names(client, areas, area_duplicate=False,
                                           check_valid_range=False)
    now_reachable = Constants.parse_passage_lock(client, areas, bilock=False)

    status = {True: 'unlocked', False: 'locked'}
    cname = client.name if client.is_staff() else client.displayname
    now0 = status[now_reachable[0]]
    name0, name1 = areas[0].name, areas[1].name

    client.send_ooc('You have {} the passage from {} to {}.'
                    .format(now0, name0, name1))
    client.send_ooc_others('(X) {} has {} the passage from {} to {} ({}).'
                           .format(cname, now0, name0, name1, client.area.id), is_staff=True)
    logger.log_server('[{}][{}]Has {} the passage from {} to {}.'
                      .format(client.area.id, client.get_char_name(), now0, name0, name1))

def ooc_cmd_uninvite(client, arg):
    """
    Removes a client based on client ID or IPID from the area's invite list.
    If given IPID, it will uninvite all clients opened by the user. Otherwise, it will just uninvite
    the given client.
    Returns an error if the given identifier does not correspond to a user.

    SYNTAX
    /uninvite <client_id>
    /uninvite <client_ipid>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)
    <client_ipid>: IPID for the client (number in parentheses in /getarea)

    EXAMPLES
    /uninvite 1                   :: Uninvites the player whose client ID is 1.
    /uninvite 1234567890          :: Uninvites all clients opened by the player whose IPID is 1234567890.
    """

    # Uninvite matching targets
    for c in Constants.parse_id_or_ipid(client, arg):
        try:
            client.area.invite_list.pop(c.ipid)
            client.send_ooc('Client {} was removed from the invite list of your area.'.format(c.id))
            c.send_ooc('You have been removed from the invite list of area {}.'.format(client.area.name))
        except (KeyError, IndexError):
            client.send_ooc('Client {} is not in the invite list.'.format(c.id))

def ooc_cmd_unlock(client, arg):
    """ (VARYING REQUIREMENTS)
    If the area is locked in some manner, attempt to perform exactly one of the following area
    unlocks in order.
    1. If player is a mod and the area is mod-locked, then mod-unlock.
    2. If player is staff and the area is gm-locked, then gm-unlock.
    3. If the area is not mod-locked nor gm-locked, then unlock.

    Returns an error if the area was locked but the unlock could not be performed (would happen due
    to insufficient permissions).

    SYNTAX
    /unlock

    PARAMETERS
    None

    EXAMPLE
    /unlock             :: Perform one of the unlocks described above if possible
    """

    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    if not client.area.is_locked and not client.area.is_modlocked and not client.area.is_gmlocked:
        raise ClientError('Area is already open.')

    if client.is_mod and client.area.is_modlocked:
        client.area.modunlock()
    elif client.is_staff() and not client.area.is_modlocked:
        client.area.gmunlock()
    elif not client.area.is_gmlocked and not client.area.is_modlocked:
        client.area.unlock()
    else:
        raise ClientError('You must be authorized to do that.')
    client.send_ooc('Area is unlocked.')

def ooc_cmd_unmute(client, arg):
    """ (CM AND MOD ONLY)
    Unmutes given user based on client ID or IPID so that they are unable to speak in IC chat.
    This command does nothing for clients that are not actively muted.
    If given IPID, it will unmute all clients opened by the user. Otherwise, it will just mute the
    given client.
    Returns an error if the given identifier does not correspond to a user.

    SYNTAX
    /unmute <client_id>
    /unmute <client_ipid>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)
    <client_ipid>: IPID for the client (number in parentheses in /getarea)

    EXAMPLES
    /unmute 1                     :: Unmutes client whose ID is 1.
    /unmute 1234567890            :: Unmutes all clients opened by the user whose IPID is 1234567890.
    """

    if not client.is_mod and not client.is_cm:
        raise ClientError('You must be authorized to do that.')

    # Mute matching targets
    for c in Constants.parse_id_or_ipid(client, arg):
        logger.log_server('Unmuted {}.'.format(c.ipid), client)
        client.area.broadcast_ooc("{} was unmuted.".format(c.displayname))
        c.is_muted = False

def ooc_cmd_unremove_h(client, arg):
    """ (MOD ONLY)
    Removes the 'Remove H' effect on all IC and OOC messages of a player by client ID (number in
    brackets) or IPID (number in parentheses).
    If given IPID, it will affect all clients opened by the user. Otherwise, it will just affect
    the given client.
    Requires /remove_h to undo.
    Returns an error if the given identifier does not correspond to a user.

    SYNTAX
    /unremove_h <client_id>
    /unremove_h <client_ipid>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)
    <client_ipid>: IPID for the client (number in parentheses in /getarea)

    EXAMPLES
    /unremove_h 1           :: Removes the 'Remove H' effect on the player whose client ID is 1.
    /unremove_h 1234567890  :: Removes the 'Remove H' effect on all clients opened by the user whose IPID is 1234567890.
    """

    if not client.is_mod:
        raise ClientError('You must be authorized to do that.')

    # Remove the 'Remove H' effect on matching targets
    for c in Constants.parse_id_or_ipid(client, arg):
        c.remove_h = False
        logger.log_server("Removed 'Remove H' effect on {}.".format(c.ipid), client)
        client.area.broadcast_ooc("{} had the 'Remove H' effect removed.".format(c.displayname))

def ooc_cmd_version(client, arg):
    """
    Obtains the current version of the server software.

    SYNTAX
    /version

    PARAMETERS
    None

    EXAMPLES
    /version        :: May return something like: This server is running TsuserverDR 4.0.0 (190801a)
    """

    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    client.send_ooc('This server is running {}.'.format(client.server.version))

def ooc_cmd_whereis(client, arg):
    """ (STAFF ONLY)
    Obtains the current area of a player by client ID (number in brackets) or IPID (number in
    parentheses).
    If given IPID, it will obtain the area info for all clients opened by the user. Otherwise, it
    will just obtain the one from the given client.
    Returns an error if the given identifier does not correspond to a user.

    SYNTAX
    /whereis <client_id>
    /whereis <client_ipid>

    PARAMETERS
    <client_id>: Client identifier (number in brackets in /getarea)
    <client_ipid>: IPID for the client (number in parentheses in /getarea)

    EXAMPLES
    Assuming client 1 with IPID 1234567890 is in the Basement (area 0)...
    /whereis 1           :: May return something like this: Client 1 (1234567890) is in Basement (0)
    /whereis 1234567890  :: May return something like this: Client 1 (1234567890) is in Basement (0)
    """

    if not client.is_staff():
        raise ClientError('You must be authorized to do that.')

    for c in Constants.parse_id_or_ipid(client, arg):
        client.send_ooc("Client {} ({}) is in {} ({})."
                        .format(c.id, c.ipid, c.area.name, c.area.id))

def ooc_cmd_whois(client, arg):
    """ (STAFF ONLY)
    Lists A LOT of a client properties. CMs and mods additionally get access to a client's HDID.
    The player can be filtered by either client ID, IPID, OOC username (in the same area),
    character name (in the same area) or custom showname (in the same area).
    If multiple clients match the given identifier, only one of them will be returned.
    For best results, use client ID (number in brackets), as this is the only tag that is
    guaranteed to be unique.
    If given no identifier, it will return your properties.
    Returns an error if the given identifier does not correspond to a user.

    SYNTAX
    /whois <target_id>

    PARAMETER
    <target_id>: Either client ID, IPID, OOC username or character name

    EXAMPLES
    For player with client ID 1, IPID 1234567890, OOC username Phantom, character name Phantom_HD, and showname The phantom, all of these do the same
    /whois 1            :: Returns client info.
    /whois 1234567890   :: Returns client info.
    /whois Phantom      :: Returns client info.
    /whois The Phantom  :: Returns client info.
    /whois Phantom_HD   :: Returns client info.
    """

    Constants.command_assert(client, arg, is_staff=True)
    if not arg:
        targets = [client]
        arg = client.id
    else:
        targets = []

    # If needed, pretend the identifier is a client ID
    if not targets and arg.isdigit():
        targets = client.server.client_manager.get_targets(client, TargetType.ID, int(arg), False)

    # If still needed, pretend the identifier is a client IPID
    if not targets and arg.isdigit():
        targets = client.server.client_manager.get_targets(client, TargetType.IPID, int(arg), False)

    # If still needed, pretend the identifier is an OOC username
    if not targets:
        targets = client.server.client_manager.get_targets(client, TargetType.OOC_NAME, arg, True)

    # If still needed, pretend the identifier is a character name
    if not targets:
        targets = client.server.client_manager.get_targets(client, TargetType.CHAR_NAME, arg, True)

    # If still needed, pretend the identifier is a showname
    if not targets:
        targets = client.server.client_manager.get_targets(client, TargetType.SHOWNAME, arg, True)

    # If still not found, too bad
    if not targets:
        raise ArgumentError('Target not found.')

    # Otherwise, send information
    info = targets[0].get_info(as_mod=client.is_mod, as_cm=client.is_cm, identifier=arg)
    client.send_ooc(info)

def ooc_cmd_8ball(client, arg):
    """
    Calls upon the wisdom of a magic 8 ball. The result is sent to all clients in the sender's area.

    SYNTAX
    /8ball

    PARAMETERS
    None

    EXAMPLES
    /8ball              :: May return something like "The magic 8 ball says You shouldn't ask that."
    """

    if len(arg) != 0:
        raise ArgumentError('This command has no arguments.')

    coin = ['yes', 'no', 'maybe', "I don't know", 'perhaps', 'please do not', 'try again',
            "you shouldn't ask that"]
    flip = random.choice(coin)
    client.area.broadcast_ooc('The magic 8 ball says {}.'.format(flip))
    logger.log_server('[{}][{}]called upon the magic 8 ball and it said {}.'
                      .format(client.area.id, client.get_char_name(), flip), client)

def ooc_cmd_narrate(client, arg):
    for c in client.area.clients:
        c.send_ic(msg=arg, as_narration=True)

def ooc_cmd_dicelog(client, arg):
    Constants.command_assert(client, arg, is_staff=True)
    if len(arg) == 0:
        arg = str(client.id)

    # Obtain target's dicelog
    target = Constants.parse_id(client, arg)
    info = target.get_dicelog()
    client.send_ooc(info)

def ooc_cmd_dicelog_area(client, arg):
    Constants.command_assert(client, arg, is_staff=True)
    if len(arg) == 0:
        arg = str(client.area.id)

    # Obtain target's dicelog
    target = Constants.parse_area_names(client, [arg])[0]
    info = target.get_dicelog()
    client.send_ooc(info)

def ooc_cmd_make_gm(client, arg):
    if not client.is_mod and not client.is_cm:
        raise ClientError('You must be authorized to do that.')
    target = Constants.parse_id(client, arg)

    if target.is_gm:
        raise ClientError('Client {} is already a GM.'.format(target.id))

    target.login(client.server.config['gmpass'], target.auth_gm, 'game master')
    client.send_ooc('Logged client {} as a GM.'.format(target.id))

def ooc_cmd_zone(client, arg):
    """ (STAFF ONLY)
    Makes a zone that spans the given area range, or just the given area if just given one area, or
    the current area if not given any.
    Returns an error if the user is already watching some other zone, or if any of the areas to be
    made part of the zone to be created already belong to some other zone.

    SYNTAX
    /zone
    /zone <sole_area_in_zone>
    /zone <area_range_start>, <area_range_end>

    PARAMETERS
    <sole_area_in_zone>: Sole area to add to the zone
    <area_range_start>: Start of area range (inclusive)
    <area_range_end>: End of area range (inclusive)

    EXAMPLES
    Assuming the player is in area 0...
    /zone                       :: Creates a zone that has area 0.
    /zone Class Trial Room 1    :: Creates a zone that only has area Class Trial Room 1
    /zone 16, 116               :: Creates a zone that has areas 16 through 116.
    """

    Constants.command_assert(client, arg, is_staff=True)
    if client.zone_watched:
        raise ClientError('You cannot create a zone while watching another.')

    # Obtain area range and create zone based on it
    raw_area_names = arg.split(', ') if arg else []
    lower_area, upper_area = Constants.parse_two_area_names(client, raw_area_names,
                                                            check_valid_range=True)
    areas = client.server.area_manager.get_areas_in_range(lower_area, upper_area)
    try:
        zone_id = client.server.zone_manager.new_zone(areas, {client})
    except ValueError: # Only possibility here is that there is an area conflict
        raise ClientError('Some of the areas of your new zone are already part of some other zone.')

    # Prepare client output
    if lower_area == upper_area:
        output = 'just area {}'.format(lower_area.id)
    else:
        output = 'areas {} through {}'.format(lower_area.id, upper_area.id)

    client.send_ooc('You have created zone `{}` containing {}.'.format(zone_id, output))

def ooc_cmd_zone_add(client, arg):
    """ (STAFF ONLY)
    Adds an area by name or ID to the zone the user is watching.
    Returns an error if the area identifier does not correspond to an area, if the area is part of
    some other zone, or if the user is not watching a zone.

    SYNTAX
    /zone_add <area_name>
    /zone_add <area_id>

    PARAMETERS
    <area_name>: Name of the area whose door you want to knock.
    <area_id>: ID of the area whose door you want to knock.

    EXAMPLES
    /zone_add 0                :: Add area 0 to the zone
    /zone_add Courtroom, 2     :: Add area "Courtroom, 2" to the zone
    """

    Constants.command_assert(client, arg, is_staff=True, parameters='=1')

def ooc_cmd_zone_delete(client, arg):
    """ (STAFF ONLY)
    Deletes a zone by zone ID, so that it is no longer part of the server's zone list.
    Returns an error if the zone identifier does not correspond to a zone.

    SYNTAX
    /zone_delete <zone_ID>

    PARAMETERS
    <zone_ID>: Identifier of zone to delete

    EXAMPLES
    /zone_delete 1000       :: Deletes the zone 1000
    """

    Constants.command_assert(client, arg, is_staff=True, parameters='=1')

def ooc_cmd_zone_global(client, arg):
    """
    Sends a global message in the OOC chat visible to all users in the zone the user area's belongs
    to who have not disabled global chat.
    Returns an error if the user has global chat off, sends an empty message, or is in an area
    not part of a zone.

    SYNTAX
    /zone_glabal <message>

    PARAMETERS
    <message>: Message to be sent

    EXAMPLE
    /zone_glabal Hello World      :: Sends Hello World to global chat.
    """

    if not arg:
        raise ArgumentError("You cannot send an empty message.")

def ooc_cmd_zone_list(client, arg):
    """ (STAFF ONLY)
    Lists all active zones in the server. For each zone, it lists details such as: zone ID,
    the number of players it has, the areas it contains, and who is watching it.
    Returns an error if there are no active zones.

    SYNTAX
    /zone_list

    PARAMETERS
    None

    EXAMPLES
    /zone_list         :: May return something like this:
    == Active zones ==
    *Zone 1000 [15] (2, 16-116). Watchers: Phantom (16)
    """

    Constants.command_assert(client, arg, is_staff=True, parameters='=0')

    info = client.server.zone_manager.get_info()
    client.send_ooc(info)

def ooc_cmd_zone_remove(client, arg):
    """ (STAFF ONLY)
    Remove an area by name or ID from the zone the user is watching.
    Returns an error if the area identifier does not correspond to an area, if the area is not part
    of the zone the user is watching, or if the user is not watching a zone.

    SYNTAX
    /zone_remove <area_name>
    /zone_remove <area_id>

    PARAMETERS
    <area_name>: Name of the area whose door you want to knock.
    <area_id>: ID of the area whose door you want to knock.

    EXAMPLES
    /zone_remove 0                :: Remove area 0 from the zone
    /zone_remove Courtroom, 2     :: Remove area "Courtroom, 2" from the zone
    """

    Constants.command_assert(client, arg, is_staff=True, parameters='=1')

def ooc_cmd_zone_unwatch(client, arg):
    """ (STAFF ONLY)
    Makes the user no longer watch the zone they are watching.
    Returns an error if the user is not watching a zone.

    SYNTAX
    /zone_unwatch

    PARAMETERS
    None

    EXAMPLES
    /zone_unwatch           :: Makes the user no longer watch their zone
    """

    Constants.command_assert(client, arg, is_staff=True, parameters='=0')
    if not client.zone_watched:
        raise ClientError('You are not watching any zone.')

    target_zone = client.zone_watched
    target_zone.remove_watcher(client)

    client.send_ooc('You are no longer watching zone `{}`.'.format(target_zone.get_id()))
    if not target_zone.get_watchers():
        client.send_ooc('As you were the last person watching it, your last zone was removed.')
    for c in target_zone.get_watchers():
        c.send_ooc('(X) {} is no longer watching your zone.'.format(client.name))

def ooc_cmd_zone_watch(client, arg):
    """ (STAFF ONLY)
    Makes the user start watching a zone by ID.
    Returns an error if the user is already watching a zone or if the zone ID does not exist.

    SYNTAX
    /zone_watch <zone_ID>

    PARAMETERS
    <zone_ID>: Identifier of zone to watch

    EXAMPLES
    /zone_watch 1000       :: Makes the user watch zone 1000
    """

    Constants.command_assert(client, arg, is_staff=True, parameters='=1')
    if client.zone_watched:
        raise ClientError('You cannot watch a zone while watching another.')

    target_zone = client.server.zone_manager.get_zone(arg)
    target_zone.add_watcher(client)

    client.send_ooc('You are now watching zone `{}`.'.format(target_zone.get_id()))
    for c in target_zone.get_watchers():
        if c == client:
            continue
        c.send_ooc('(X) {} is now watching your zone.'.format(client.name))

def ooc_cmd_exec(client, arg):
    """
    VERY DANGEROUS. SHOULD ONLY BE ENABLED FOR DEBUGGING.

    DID I MENTION THIS IS VERY DANGEROUS?

    DO NOT ENABLE THIS FUNCTION UNLESS YOU KNOW WHAT YOU ARE DOING.

    I MEAN IT.

    PEOPLE WILL BREAK YOUR SERVER AND POSSIBLY THE HOST MACHINE IT IS ON IF YOU KEEP IT ON.

    DO NOT BE STUPID.

    Executes a Python expression and returns the evaluated expression.
    If passed in a Python statement, it will execute code in the global environment.
    Returns an error if the expression would raise an error in a normal Python environment.

    SYNTAX
    /exec <command>

    PARAMETERS
    <command>

    EXAMPLES
    /exec 1+1                                           :: Returns 2
    /exec while True: client.send_ooc("Hi")             :: Commit sudoku
    """

    # IF YOU WANT TO DISABLE /exec: SET debug TO 0 (debug = 0)
    # IF YOU WANT TO ENABLE /exec: SET debug TO 1 (debug = 1)
    debug = 0
    if not debug:
        return None

    logger.log_print("Attempting to run instruction {}".format(arg))

    try:
        client.server.send_all_cmd_pred('CT', '>>>', arg, pred=lambda c: c == client)
        result = eval(arg)
        if result is not None:
            client.server.send_all_cmd_pred('CT', '', result, pred=lambda c: c == client)
    except Exception:
        try:
            # Temporarily add "client" as a global variable, to allow using
            # expressions such as client.send_ooc("Hi")
            globals()['client'] = client
            exec(arg, globals())
            #client.send_ooc("Executed {}".format(arg))
        except Exception as e:
            try:
                client.server.send_all_cmd_pred('CT', '',
                                                'Python error: {}: {}'.format(type(e).__name__, e),
                                                pred=lambda c: c == client)
            except Exception:
                pass
    globals().pop('client', None) # Don't really want "client" to be a global variable
    return 1    # Indication that /exec is live
