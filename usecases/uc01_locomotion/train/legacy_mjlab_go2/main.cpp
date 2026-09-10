#include "FSM/CtrlFSM.h"
#include "FSM/State_Passive.h"
#include "FSM/State_FixStand.h"
#include "FSM/State_RLBase.h"

std::unique_ptr<LowCmd_t> FSMState::lowcmd = nullptr;
std::shared_ptr<LowState_t> FSMState::lowstate = nullptr;
std::shared_ptr<Keyboard> FSMState::keyboard = nullptr;

void init_fsm_state()
{
    FSMState::lowcmd = std::make_unique<LowCmd_t>();
    FSMState::lowstate = std::make_shared<LowState_t>();
    spdlog::info("Waiting for connection to robot...");
    FSMState::lowstate->wait_for_connection();
    spdlog::info("Connected to robot.");
}

int main(int argc, char** argv)
{
    auto vm = param::helper(argc, argv);
    std::cout << " --- Unitree Robotics --- \n";
    std::cout << "     Go2 Controller (auto-transition build) \n";

    unitree::robot::ChannelFactory::Instance()->Init(0, vm["network"].as<std::string>());
    init_fsm_state();

    auto fsm = std::make_unique<CtrlFSM>(param::config["FSM"]);
    fsm->start();

    // === AUTO-TRANSITION (sin mando) ===
    spdlog::info("Auto-transition mode. No joystick required.");
    spdlog::info("Sequence: Passive -> FixStand (2s) -> Velocity (4s)");

    // Espera 2 segundos en Passive para asegurar buena recepción de LowState
    sleep(2);
    spdlog::info("Switching to FixStand...");
    fsm->switchTo("FixStand");

    // Espera 4 segundos en FixStand para que el robot se estabilice de pie
    sleep(6);
    spdlog::info("Switching to Velocity (RL policy active)...");
    fsm->switchTo("Velocity");

    spdlog::info("Robot in Velocity mode. RL policy controlling. Ctrl+C to exit.");

    while (true)
    {
        sleep(1);
    }
    return 0;
}
