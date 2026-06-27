from releaser.bump import semver


def test_semver_parse_and_finalize():
    v = semver.parse("1.2.3-rc.1+build.5")
    assert v.major == 1 and v.minor == 2 and v.patch == 3
    assert v.pre == "rc.1"
    assert v.meta == "build.5"
    assert semver.finalize("1.2.3-rc.1") == "1.2.3"


def test_semver_parse_pep440_rc_style():
    # PEP 440-style pre-release without hyphen (e.g. 1.2.3rc1)
    v = semver.parse("1.2.3rc1")
    assert v.major == 1 and v.minor == 2 and v.patch == 3
    assert v.pre == "rc1"
    assert semver.finalize("1.2.3rc1") == "1.2.3"


def test_semver_parse_dot_rc_style():
    # Dotted pre-release separator (e.g. 1.0.0.rc10) -> pre normalized to "rc10"
    v = semver.parse("1.0.0.rc10")
    assert v.major == 1 and v.minor == 0 and v.patch == 0
    assert v.pre == "rc10"
    assert semver.finalize("1.0.0.rc10") == "1.0.0"
    # Dotted separator with numbered identifier (e.g. 2.0.0.beta.5)
    assert semver.parse("2.0.0.beta.5").pre == "beta.5"


def test_semver_apply_prerelease_continue_from_dot_rc():
    # Continuing from a dotted rc form should increment the numeric suffix
    v = semver.apply_prerelease(
        "1.0.0", previous_version="1.0.0.rc10", channel="rc", auto_increment=True
    )
    assert v == "1.0.0-rc.11"


def test_semver_bump_base():
    assert semver.bump_base("1.2.3", "patch") == "1.2.4"
    assert semver.bump_base("1.2.3", "minor") == "1.3.0"
    assert semver.bump_base("1.2.3", "major") == "2.0.0"


def test_semver_apply_prerelease_increment():
    # Start pre-release sequence
    v1 = semver.apply_prerelease(
        "1.2.3", previous_version=None, channel="rc", auto_increment=True
    )
    assert v1 == "1.2.3-rc.1"
    # Continue sequence from canonical rc.N form
    v2 = semver.apply_prerelease(
        "1.2.3", previous_version=v1, channel="rc", auto_increment=True
    )
    assert v2 == "1.2.3-rc.2"
    # Continue sequence from legacy rcN form
    v3 = semver.apply_prerelease(
        "1.2.3", previous_version="1.2.3-rc1", channel="rc", auto_increment=True
    )
    assert v3 == "1.2.3-rc.2"
