from releaser.bump import semver


def test_semver_parse_and_finalize():
    v = semver.parse("1.2.3-rc.1+build.5")
    assert v.major == 1 and v.minor == 2 and v.patch == 3
    assert v.pre == "rc.1"
    assert v.meta == "build.5"
    assert semver.finalize("1.2.3-rc.1") == "1.2.3"


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
    # Continue sequence
    v2 = semver.apply_prerelease(
        "1.2.3", previous_version=v1, channel="rc", auto_increment=True
    )
    assert v2 == "1.2.3-rc.2"
