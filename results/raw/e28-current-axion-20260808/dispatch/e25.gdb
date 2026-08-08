set pagination off
set breakpoint pending on
break ggml_gemv_q4_K_8x4_q8_K_decoded
commands
silent
printf "E28_DISPATCH e25 symbol=ggml_gemv_q4_K_8x4_q8_K_decoded n=%d nc=%d\n", n, nc
bt 4
quit
end
run
