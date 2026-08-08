set pagination off
set breakpoint pending on
break ggml_gemv_q4_K_8x4_q8_K_decoded
commands
silent
printf "E25_SHAPE n=%d nc=%d\n", n, nc
continue
end
run
