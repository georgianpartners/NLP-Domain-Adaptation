#!/bin/sh
SESSION='autonlp'

# Find or create a tmux session
if tmux has-session -t $SESSION 2> /dev/null; then
    tmux attach-session -t $SESSION -d
else
    tmux new-session -s $SESSION -d
fi

# Training panes
DPT_COMPLETIONS=( 10 25 50 75 )
for DPT_COMPLETION in ${DPT_COMPLETIONS[@]}; do
    tmux split-window -v
    tmux send-keys "echo $DPT_COMPLETION" C-m
    # tmux send-keys "source activate pytorch_p36" C-m
    # tmux send-keys "./run_pipeline.sh $DPT_COMPLETION" C-m
    tmux select-layout even-vertical
done
tmux kill-pane -t 0
tmux select-layout even-vertical


# Second pane for htop
tmux split-window -v
tmux send-keys "htop" C-m

# Third pane for GPU usage
tmux split-window -h
tmux send-keys "watch -n 1 nvidia-smi" C-m