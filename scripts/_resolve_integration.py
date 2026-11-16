"""Resolve the P7 merge conflicts by unioning both sides' route blocks."""
import re
import sys

APP = "web/app.py"

text = open(APP).read()  # read fully before writing

resolved_block = '''@app.route('/api/guardian/killswitch', methods=['GET'])
@login_required
def api_guardian_killswitch_status():
    """Owner-only: current emergency kill-switch state."""
    user_id = session['user_id']
    if not _is_owner(user_id):
        return jsonify({'error': 'owner access required'}), 403
    from genesis_protocol.guardian import get_kill_switch

    return jsonify(get_kill_switch().status())


@app.route('/api/guardian/killswitch', methods=['POST'])
@login_required
def api_guardian_killswitch_set():
    """Owner-only: engage or disengage the emergency kill switch.

    Engaging stops all automatic defence. Disengaging resumes it and is an owner
    action, so it is gated here and never automatic.
    """
    user_id = session['user_id']
    if not _is_owner(user_id):
        return jsonify({'error': 'owner access required'}), 403
    from genesis_protocol.guardian import get_kill_switch

    data = request.get_json(silent=True) or {}
    engage = bool(data.get('engage', True))
    switch = get_kill_switch()
    if engage:
        return jsonify(switch.engage(reason=data.get('reason') or 'owner request', actor=str(user_id)))
    try:
        return jsonify(switch.disengage(owner_approved=True, actor=str(user_id),
                                        reason=data.get('reason') or 'owner resumed'))
    except PermissionError:
        return jsonify({'error': 'owner approval required'}), 403


@app.route('/api/guardian/defend', methods=['POST'])
@login_required
def api_guardian_defend():
    """Owner-only: run one bounded defence pass over supplied findings.

    Performs only low-risk, reversible, allow-listed actions inside budget, when
    the kill switch is off. Everything else is returned as a proposal. It never
    deletes data, rotates a credential, deploys or changes policy.
    """
    user_id = session['user_id']
    if not _is_owner(user_id):
        return jsonify({'error': 'owner access required'}), 403
    from genesis_protocol.guardian import DefenceEngine, LocalActionSink

    data = request.get_json(silent=True) or {}
    findings = data.get('findings') or []
    if not isinstance(findings, list):
        return jsonify({'error': 'findings must be a list'}), 400
    engine = DefenceEngine(action_sink=LocalActionSink())
    return jsonify(engine.defend(findings).to_dict())


@app.route('/api/guardian/actions', methods=['GET'])
@login_required
def api_guardian_actions():
    """Owner-only: the allow-list of permitted defensive actions."""
    user_id = session['user_id']
    if not _is_owner(user_id):
        return jsonify({'error': 'owner access required'}), 403
    from genesis_protocol.guardian import NEVER_ACTIONS, ActionCatalog

    return jsonify({'allowed': ActionCatalog().all_specs(), 'never': sorted(NEVER_ACTIONS)})


@app.route('/api/coordination/status', methods=['GET'])
@login_required
def api_coordination_status():
    """Owner-only: coordination status (agents, tasks, messages, providers)."""
    user_id = session['user_id']
    if not _is_owner(user_id):
        return jsonify({'error': 'owner access required'}), 403
    from genesis_protocol.coordination import get_coordination_manager

    return jsonify(get_coordination_manager().status())


@app.route('/api/coordination/manifests', methods=['GET'])
@login_required
def api_coordination_manifests():
    """Owner-only: capability manifests for every registered agent."""
    user_id = session['user_id']
    if not _is_owner(user_id):
        return jsonify({'error': 'owner access required'}), 403
    from genesis_protocol.coordination import get_coordination_manager

    return jsonify({'manifests': get_coordination_manager().manifests()})


@app.route('/api/coordination/authorize', methods=['POST'])
@login_required
def api_coordination_authorize():
    """Owner-only: dry-run an authorization decision for an interface/principal.

    Read-only: it answers whether a tool call would be allowed, without performing
    it, so the same decision can be checked before wiring a new interface.
    """
    user_id = session['user_id']
    if not _is_owner(user_id):
        return jsonify({'error': 'owner access required'}), 403
    from genesis_protocol.coordination import get_coordination_manager

    data = request.get_json(silent=True) or {}
    interface = data.get('interface') or 'web'
    tool = data.get('tool')
    if not tool:
        return jsonify({'error': 'tool is required'}), 400
    manager = get_coordination_manager()
    return jsonify(manager.authorize(interface, data.get('principal', user_id), tool,
                                     agent_id=data.get('agent_id'),
                                     owner_approved=bool(data.get('owner_approved'))))'''

# Replace the whole conflicted region (both hunks) with the union block. The
# union block already contains the shared docstring/owner-check lines that sit
# between git's two hunks, so replacing the full span is correct.
start = text.index("<<<<<<< HEAD\n")
end = text.rindex(">>>>>>> origin/feat/v7-p7-coordination\n") + len(
    ">>>>>>> origin/feat/v7-p7-coordination\n"
)
text = text[:start] + resolved_block + "\n\n\n" + text[end:]
open(APP, "w").write(text)
print("web/app.py resolved, lines:", len(text.split(chr(10))))
