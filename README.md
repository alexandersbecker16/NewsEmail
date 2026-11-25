# Daily News Brief

Emails five news headlines once a day. The schedule runs from the Gmail account you choose, so the computer can be closed, asleep, or shut down.

## Start

1. Install [Python 3.12 or newer](https://www.python.org/downloads/) and leave **Add python.exe to PATH** checked.
2. Clone this repository and open the folder.
3. Double-click `start_dashboard.bat` and leave that window open.
4. Enter the send time, who should receive the brief, and the Gmail account it should come from.
5. Click **On**. The first time, approve the Google window with that same Gmail account, then click **I've finished the Google page**.
6. Click **Off** any time you want the emails to stop. Off takes effect right away.

Your settings stay in `config.json` on your computer. That file is not part of this repository, so a fresh clone starts blank and off.

A Gmail [app password](https://support.google.com/accounts/answer/185833) is only for sending a test from this computer. The daily email uses the Google approval from step 5.

Each send time produces one email. Opening the computer does not send another.
