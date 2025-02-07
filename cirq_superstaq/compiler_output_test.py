import importlib
import pickle
import textwrap
from unittest import mock

import cirq
import general_superstaq as gss
import pytest

import cirq_superstaq as css


def test_active_qubit_indices() -> None:
    qubits = cirq.LineQubit.range(6)

    circuit = cirq.Circuit(
        cirq.X(qubits[5]),
        cirq.CZ(qubits[3], qubits[1]),
        css.barrier(*qubits),
        cirq.H(qubits[1]),
    )

    assert css.active_qubit_indices(circuit) == [1, 3, 5]

    with pytest.raises(ValueError, match="line qubits"):
        _ = css.active_qubit_indices(cirq.Circuit(cirq.X(cirq.GridQubit(1, 2))))


def test_compiler_output_repr() -> None:
    circuit = cirq.Circuit()
    assert (
        repr(css.compiler_output.CompilerOutput(circuit))
        == f"CompilerOutput({circuit!r}, None, None, None, None)"
    )

    circuits = [circuit, circuit]
    assert (
        repr(css.compiler_output.CompilerOutput(circuits))
        == f"CompilerOutput({circuits!r}, None, None, None, None)"
    )


def test_read_json_ibmq() -> None:
    q0 = cirq.LineQubit(0)
    circuit = cirq.Circuit(cirq.H(q0), cirq.measure(q0))

    json_dict = {
        "cirq_circuits": css.serialization.serialize_circuits(circuit),
        "pulses": gss.serialization.serialize([mock.DEFAULT]),
    }

    out = css.compiler_output.read_json_ibmq(json_dict, circuits_is_list=False)
    assert out.circuit == circuit
    assert out.pulse_sequence == mock.DEFAULT
    assert not hasattr(out, "circuits")
    assert not hasattr(out, "pulse_sequences")

    out = css.compiler_output.read_json_ibmq(json_dict, circuits_is_list=True)
    assert out.circuits == [circuit]
    assert out.pulse_sequences == [mock.DEFAULT]
    assert not hasattr(out, "circuit")
    assert not hasattr(out, "pulse_sequence")

    with mock.patch.dict("sys.modules", {"qiskit": None}), pytest.warns(
        UserWarning, match="requires Qiskit Terra"
    ):
        out = css.compiler_output.read_json_ibmq(json_dict, circuits_is_list=False)
        assert out.circuit == circuit
        assert out.pulse_sequence is None

    with mock.patch("qiskit.__version__", "0.17.2"), pytest.warns(
        UserWarning, match="you have 0.17.2"
    ):
        out = css.compiler_output.read_json_ibmq(json_dict, circuits_is_list=True)
        assert out.circuits == [circuit]
        assert out.pulse_sequences is None


@mock.patch.dict("sys.modules", {"qtrl": None})
def test_read_json_aqt() -> None:
    importlib.reload(css.compiler_output)

    qubits = cirq.LineQubit.range(4)
    circuit = cirq.Circuit(cirq.H.on_each(*qubits), cirq.measure(*qubits))
    state_str = gss.serialization.serialize({})
    pulse_lists_str = gss.serialization.serialize([[[]]])

    json_dict = {
        "cirq_circuits": css.serialization.serialize_circuits(circuit),
        "state_jp": state_str,
        "pulse_lists_jp": pulse_lists_str,
    }

    out = css.compiler_output.read_json_aqt(json_dict, circuits_is_list=False)
    assert out.circuit == circuit
    assert not hasattr(out, "circuits")

    out = css.compiler_output.read_json_aqt(json_dict, circuits_is_list=True)
    assert out.circuits == [circuit]
    assert not hasattr(out, "circuit")

    # multiple circuits
    pulse_lists_str = gss.serialization.serialize([[[]], [[]]])
    json_dict = {
        "cirq_circuits": css.serialization.serialize_circuits([circuit, circuit]),
        "state_jp": state_str,
        "pulse_lists_jp": pulse_lists_str,
    }
    out = css.compiler_output.read_json_aqt(json_dict, circuits_is_list=True)
    assert out.circuits == [circuit, circuit]
    assert not hasattr(out, "circuit")


def test_read_json_with_qtrl() -> None:  # pragma: no cover, b/c test requires qtrl installation
    qtrl = pytest.importorskip("qtrl", reason="qtrl not installed")
    seq = qtrl.sequencer.Sequence(n_elements=1)

    circuit = cirq.Circuit(cirq.H(cirq.LineQubit(4)))
    state_str = gss.serialization.serialize(seq.__getstate__())
    pulse_lists_str = gss.serialization.serialize([[[]]])
    json_dict = {
        "cirq_circuits": css.serialization.serialize_circuits(circuit),
        "state_jp": state_str,
        "pulse_lists_jp": pulse_lists_str,
    }

    out = css.compiler_output.read_json_aqt(json_dict, circuits_is_list=False)
    assert out.circuit == circuit
    assert isinstance(out.seq, qtrl.sequencer.Sequence)
    assert pickle.dumps(out.seq) == pickle.dumps(seq)
    assert out.pulse_list == [[]]
    assert not hasattr(out.seq, "_readout")
    assert not hasattr(out, "circuits") and not hasattr(out, "pulse_lists")

    # Serialized readout attribute for aqt_zurich_qpu:
    json_dict["readout_jp"] = state_str
    out = css.compiler_output.read_json_aqt(json_dict, circuits_is_list=False)
    assert out.circuit == circuit
    assert out.pulse_list == [[]]
    assert isinstance(out.seq, qtrl.sequencer.Sequence)
    assert pickle.dumps(out.seq._readout) == pickle.dumps(out.seq) == pickle.dumps(seq)

    # Multiple circuits:
    out = css.compiler_output.read_json_aqt(json_dict, circuits_is_list=True)
    assert out.circuits == [circuit]
    assert pickle.dumps(out.seq) == pickle.dumps(seq)
    assert out.pulse_lists == [[[]]]
    assert not hasattr(out, "circuit") and not hasattr(out, "pulse_list")

    pulse_lists_str = gss.serialization.serialize([[[]], [[]]])
    json_dict = {
        "cirq_circuits": css.serialization.serialize_circuits([circuit, circuit]),
        "state_jp": state_str,
        "pulse_lists_jp": pulse_lists_str,
    }
    out = css.compiler_output.read_json_aqt(json_dict, circuits_is_list=True)
    assert out.circuits == [circuit, circuit]
    assert pickle.dumps(out.seq) == pickle.dumps(seq)
    assert out.pulse_lists == [[[]], [[]]]
    assert not hasattr(out, "circuit") and not hasattr(out, "pulse_list")


def test_read_json_qscout() -> None:
    q0 = cirq.LineQubit(0)
    circuit = cirq.Circuit(cirq.H(q0), cirq.measure(q0))

    jaqal_program = textwrap.dedent(
        """\
        register allqubits[1]
        prepare_all
        R allqubits[0] -1.5707963267948966 1.5707963267948966
        Rz allqubits[0] -3.141592653589793
        measure_all
        """
    )

    json_dict = {
        "cirq_circuits": css.serialization.serialize_circuits(circuit),
        "jaqal_programs": [jaqal_program],
    }

    out = css.compiler_output.read_json_qscout(json_dict, circuits_is_list=False)
    assert out.circuit == circuit
    assert out.jaqal_program == jaqal_program
    assert not hasattr(out, "jaqal_programs")

    json_dict = {
        "cirq_circuits": css.serialization.serialize_circuits([circuit, circuit]),
        "jaqal_programs": [jaqal_program, jaqal_program],
    }
    out = css.compiler_output.read_json_qscout(json_dict, circuits_is_list=True)
    assert out.circuits == [circuit, circuit]
    assert out.jaqal_programs == json_dict["jaqal_programs"]
    assert not hasattr(out, "jaqal_program")


def test_read_json_only_circuits() -> None:
    q0 = cirq.LineQubit(0)
    circuit = cirq.Circuit(cirq.H(q0), cirq.measure(q0))

    json_dict = {
        "cirq_circuits": css.serialization.serialize_circuits(circuit),
    }

    out = css.compiler_output.read_json_only_circuits(json_dict, circuits_is_list=False)
    assert out.circuit == circuit

    json_dict = {
        "cirq_circuits": css.serialization.serialize_circuits([circuit, circuit]),
    }
    out = css.compiler_output.read_json_only_circuits(json_dict, circuits_is_list=True)
    assert out.circuits == [circuit, circuit]
