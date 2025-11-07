from utility import in_meeting

while True:
    meeting = in_meeting()
    print(meeting)
    assert not meeting