#pragma once

#include "unitree/dds_wrapper/robots/go2/go2.h"
#include "unitree/dds_wrapper/common/crc.h"
#include <unitree/robot/channel/channel_publisher.hpp>
#include <unitree/idl/go2/LowCmd_.hpp>
#include <mutex>

class SimpleLowCmdPublisher
{
public:
    using MsgType = unitree_go::msg::dds_::LowCmd_;

    MsgType msg_{};

    explicit SimpleLowCmdPublisher(std::string topic = "rt/lowcmd")
    : publisher_(std::make_shared<unitree::robot::ChannelPublisher<MsgType>>(topic))
    {
        msg_.head()[0] = 0xFE;
        msg_.head()[1] = 0xEF;
        msg_.level_flag() = 0xFF;
        msg_.gpio() = 0;

        for(auto & motor : msg_.motor_cmd())
        {
            motor.mode() = 0x01;
            motor.q() = PosStopF;
            motor.dq() = VelStopF;
            motor.kp() = 0.0f;
            motor.kd() = 0.0f;
            motor.tau() = 0.0f;
        }

        publisher_->InitChannel();
    }

    void lock()
    {
        mutex_.lock();
    }

    void unlock()
    {
        mutex_.unlock();
    }

    bool trylock()
    {
        return mutex_.try_lock();
    }

    void unlockAndPublish()
    {
        msg_.crc() = crc32_core((uint32_t*)&msg_, (sizeof(MsgType) >> 2) - 1);
        publisher_->Write(msg_);
        mutex_.unlock();
    }

private:
    static constexpr float PosStopF = 2.146e9f;
    static constexpr float VelStopF = 16000.0f;

    std::mutex mutex_;
    unitree::robot::ChannelPublisherPtr<MsgType> publisher_;
};

using LowCmd_t = SimpleLowCmdPublisher;
using LowState_t = unitree::robot::go2::subscription::LowState;
