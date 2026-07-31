// SPDX-License-Identifier: Apache-2.0

#include "Llm.hpp"

#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <string>

#include <nlohmann/json.hpp>

namespace {

using Clock = std::chrono::steady_clock;
using Json = nlohmann::json;

struct Arguments {
    std::filesystem::path model;
    std::filesystem::path tasks;
    std::filesystem::path output;
    std::string sharedLibraryPath;
    int threads{4};
    int context{2048};
    int maxOutputTokens{8};
};

std::string RequireValue(int& index, int argc, char** argv)
{
    if (++index >= argc) {
        throw std::invalid_argument(std::string("missing value for ") + argv[index - 1]);
    }
    return argv[index];
}

Arguments ParseArguments(int argc, char** argv)
{
    Arguments arguments;
    for (int index = 1; index < argc; ++index) {
        const std::string option = argv[index];
        if (option == "--model") {
            arguments.model = RequireValue(index, argc, argv);
        } else if (option == "--tasks") {
            arguments.tasks = RequireValue(index, argc, argv);
        } else if (option == "--output") {
            arguments.output = RequireValue(index, argc, argv);
        } else if (option == "--shared-library-path") {
            arguments.sharedLibraryPath = RequireValue(index, argc, argv);
        } else if (option == "--threads") {
            arguments.threads = std::stoi(RequireValue(index, argc, argv));
        } else if (option == "--context") {
            arguments.context = std::stoi(RequireValue(index, argc, argv));
        } else if (option == "--max-output-tokens") {
            arguments.maxOutputTokens = std::stoi(RequireValue(index, argc, argv));
        } else {
            throw std::invalid_argument("unknown option: " + option);
        }
    }
    if (arguments.model.empty() || arguments.tasks.empty() || arguments.output.empty()) {
        throw std::invalid_argument("--model, --tasks, and --output are required");
    }
    if (arguments.threads <= 0 || arguments.context <= 0 ||
        arguments.maxOutputTokens <= 0) {
        throw std::invalid_argument("numeric options must be positive");
    }
    return arguments;
}

Json ReadJson(const std::filesystem::path& path)
{
    std::ifstream stream(path);
    if (!stream) {
        throw std::runtime_error("cannot open JSON file: " + path.string());
    }
    return Json::parse(stream);
}

std::string TerminationName(LLM::TerminationReason reason)
{
    switch (reason) {
        case LLM::TerminationReason::None:
            return "token_limit";
        case LLM::TerminationReason::BackendEos:
            return "backend_eos";
        case LLM::TerminationReason::StopWord:
            return "stop_word";
        case LLM::TerminationReason::ContextFull:
            return "context_full";
        case LLM::TerminationReason::Cancelled:
            return "cancelled";
    }
    return "unknown";
}

double Milliseconds(Clock::time_point start, Clock::time_point end)
{
    return std::chrono::duration<double, std::milli>(end - start).count();
}

Json RunTasks(const Arguments& arguments)
{
    const Json taskManifest = ReadJson(arguments.tasks);
    if (taskManifest.value("schema_version", 0) != 1 ||
        !taskManifest.contains("instruction") || !taskManifest.contains("tasks") ||
        !taskManifest["tasks"].is_array()) {
        throw std::invalid_argument("invalid E3 task manifest");
    }

    Json config = {
        {"chat",
         {{"systemPrompt", ""},
          {"applyDefaultChatTemplate", false},
          {"systemTemplate", "%s"},
          {"userTemplate", "%s"}}},
        {"model", {{"llmModelName", arguments.model.string()}, {"isVision", false}}},
        {"runtime",
         {{"batchSize", 256},
          {"numThreads", arguments.threads},
          {"contextSize", arguments.context}}},
        {"stopWords", {"<|im_end|>", "<|endoftext|>", "<eos>"}},
    };

    LlmConfig llmConfig(config.dump());
    LLM llm;
    const auto loadStart = Clock::now();
    llm.LlmInit(llmConfig, arguments.sharedLibraryPath);
    const auto loadEnd = Clock::now();

    Json cases = Json::array();
    const std::string instruction = taskManifest.at("instruction").get<std::string>();
    for (const auto& task : taskManifest.at("tasks")) {
        llm.ResetContext();
        const std::string prompt =
            instruction + "\n\n" + task.at("prompt").get<std::string>();
        LlmChat::Payload payload{prompt, "", true};

        const auto encodeStart = Clock::now();
        llm.Encode(payload);
        const auto encodeEnd = Clock::now();

        std::string response;
        int generatedTokens = 0;
        std::string terminationReason = "token_limit";
        const auto decodeStart = Clock::now();
        for (; generatedTokens < arguments.maxOutputTokens; ++generatedTokens) {
            const std::optional<LLM::TextTokenId> token = llm.NextTokenId();
            if (!token.has_value()) {
                terminationReason = TerminationName(llm.GetLastTerminationReason());
                break;
            }
            const std::string piece = llm.DetokenizeTextToken(*token);
            if (llm.IsStopTextPiece(piece)) {
                terminationReason = "stop_word";
                break;
            }
            response += piece;
        }
        const auto decodeEnd = Clock::now();

        cases.push_back(
            {{"id", task.at("id")},
             {"response", response},
             {"generated_tokens", generatedTokens},
             {"encode_ms", Milliseconds(encodeStart, encodeEnd)},
             {"decode_ms", Milliseconds(decodeStart, decodeEnd)},
             {"termination_reason", terminationReason}});
    }
    llm.FreeLlm();

    return {
        {"schema_version", 1},
        {"framework", LLM::GetFrameworkType()},
        {"model_path", arguments.model.string()},
        {"threads", arguments.threads},
        {"context_size", arguments.context},
        {"max_output_tokens", arguments.maxOutputTokens},
        {"chat_template_mode", "framework_auto"},
        {"model_load_ms", Milliseconds(loadStart, loadEnd)},
        {"cases", cases},
    };
}

}  // namespace

int main(int argc, char** argv)
{
    try {
        const Arguments arguments = ParseArguments(argc, argv);
        const Json output = RunTasks(arguments);
        if (!arguments.output.parent_path().empty()) {
            std::filesystem::create_directories(arguments.output.parent_path());
        }
        std::ofstream stream(arguments.output);
        if (!stream) {
            throw std::runtime_error("cannot open output file: " + arguments.output.string());
        }
        stream << output.dump(2) << '\n';
        std::cout << arguments.output << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "e3-quality-cli: " << error.what() << '\n';
        return 1;
    }
}
